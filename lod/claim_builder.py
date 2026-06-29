"""Centralized construction of Wikibase claim data structures.

This module provides ``ClaimBuilder`` — a stateless helper that converts
property values into the JSON representation used by the Wikibase
``editEntity`` batch API. It supports all property types currently used by
``lod.wikibase`` and removes the duplication between ``add_claim`` and
``add_qualifier_data``.
"""

import re
from typing import Any, Dict, Optional, Tuple

from .errors import ValidationError


class ClaimBuilder:
    """Build Wikibase claim / qualifier data dicts for the batch API.

    Args:
        properties_map: Mapping from property ID (e.g. ``"P1"``) to its
            Wikibase datatype (e.g. ``"WikibaseItem"``, ``"Time"``).
        host: Wikibase host used for quantity unit URIs (without protocol).
        default_language: Language code used for ``Monolingualtext`` values.
        calendar: URI of the calendar model for ``Time`` values.
    """

    def __init__(
        self,
        properties_map: Dict[str, str],
        host: str,
        *,
        default_language: str = "cs",
        calendar: str = "http://www.wikidata.org/entity/Q1985727",
    ):
        self.properties_map = properties_map
        self.host = host
        self.default_language = default_language
        self.calendar = calendar

    def build_claim(
        self,
        property_id: str,
        value: Any,
        *,
        rank: str = "normal",
        unit: Optional[str] = None,
        references: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a complete claim dict for ``editEntity``.

        Args:
            references: Optional reference snaks. Supported forms:
                - List of ``(property_id, value)`` tuples grouped into a single
                  reference block.
                - List of dicts mapping property IDs to values grouped into a
                  single reference block.

        Returns ``None`` when the value cannot be converted (e.g. an invalid
        date string).

        Raises:
            ValidationError: If the property is unknown.
        """
        mainsnak = self.build_mainsnak(property_id, value, unit=unit)
        if mainsnak is None:
            return None

        claim = {
            "mainsnak": mainsnak,
            "type": "statement",
            "rank": rank,
        }
        refs = self._build_references(references)
        if refs:
            claim["references"] = refs
        return claim

    def build_mainsnak(
        self,
        property_id: str,
        value: Any,
        *,
        unit: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build only the ``mainsnak`` part of a claim."""
        prop_type = self._require_property_type(property_id)
        builder = self._DISPATCH.get(prop_type, self._build_string)
        datavalue = builder(property_id, value, unit=unit)
        if datavalue is None:
            return None

        return {
            "snaktype": "value",
            "property": property_id,
            "datavalue": datavalue,
        }

    def build_qualifier(
        self,
        property_id: str,
        value: Any,
    ) -> Optional[Dict[str, Any]]:
        """Build a qualifier snak.

        Qualifiers use the same value encoding as mainsnaks, but they never
        carry ``rank`` or ``unit``.
        """
        prop_type = self._require_property_type(property_id)
        builder = self._DISPATCH.get(prop_type, self._build_string)
        datavalue = builder(property_id, value, unit=None)
        if datavalue is None:
            return None

        return {
            "snaktype": "value",
            "property": property_id,
            "datavalue": datavalue,
        }

    def _require_property_type(self, property_id: str) -> str:
        prop_type = self.properties_map.get(property_id)
        if prop_type is None:
            raise ValidationError(
                f"Unknown property {property_id}. "
                "Run list_properties() or check the property ID.",
                field="property_id",
                value=property_id,
            )
        return prop_type

    @property
    def _DISPATCH(self) -> Dict[str, Any]:
        # Kept as a property so subclasses can override it easily.
        return {
            "WikibaseItem": self._build_item,
            "Time": self._build_time,
            "Quantity": self._build_quantity,
            "String": self._build_string,
            "ExternalId": self._build_string,
            "Url": self._build_string,
            "url": self._build_string,
            "Monolingualtext": self._build_monolingualtext,
        }

    def _build_item(self, _property_id: str, value: Any, **kwargs) -> Dict[str, Any]:
        item_id = str(value).replace("Q", "")
        if not item_id.isdigit():
            raise ValidationError(
                f"Invalid item value {value!r} for {_property_id}",
                field=_property_id,
                value=str(value),
            )
        return {
            "value": {
                "entity-type": "item",
                "numeric-id": item_id,
            },
            "type": "wikibase-entityid",
        }

    def _build_string(self, _property_id: str, value: Any, **kwargs) -> Dict[str, Any]:
        return {
            "value": str(value).strip(),
            "type": "string",
        }

    def _build_monolingualtext(
        self,
        _property_id: str,
        value: Any,
        **kwargs,
    ) -> Dict[str, Any]:
        return {
            "value": {
                "text": str(value).strip(),
                "language": self.default_language,
            },
            "type": "monolingualtext",
        }

    def _build_time(self, _property_id: str, value: Any, **kwargs) -> Optional[Dict[str, Any]]:
        value = str(value).strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            time = value
            precision = 11
        elif re.match(r"\d{4}-\d{2}", value):
            time = value + "-00"
            precision = 10
        elif re.match(r"\d{4}", value):
            time = value + "-00-00"
            precision = 9
        else:
            return None

        return {
            "value": {
                "time": "+" + time + "T00:00:00Z",
                "precision": precision,
                "calendarmodel": self.calendar,
                "timezone": 0,
                "after": 0,
                "before": 0,
            },
            "type": "time",
        }

    def _build_quantity(
        self,
        _property_id: str,
        value: Any,
        *,
        unit: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        amount = str(value).lstrip("+").strip()
        if unit:
            unit_id = str(unit).replace("Q", "")
            unit_uri = f"http://{self.host}/entity/Q{unit_id}"
        else:
            # Dimensionless / plain number.
            unit_uri = "1"

        return {
            "value": {
                "amount": "+" + amount,
                "unit": unit_uri,
            },
            "type": "quantity",
        }

    def _build_references(
        self,
        references: Optional[Any],
    ) -> Optional[list]:
        """Convert reference definitions into Wikibase reference blocks.

        Supported input forms:
        - ``[(property_id, value), ...]`` -> single reference with multiple snaks.
        - ``[{"property_id": value, ...}]`` -> single reference with multiple snaks.
        """
        if not references:
            return None

        snaks: Dict[str, list] = {}
        for ref in references:
            if isinstance(ref, (list, tuple)) and len(ref) == 2:
                ref_property, ref_value = ref
            elif isinstance(ref, dict) and "property" in ref and "value" in ref:
                ref_property = ref["property"]
                ref_value = ref["value"]
            elif isinstance(ref, dict):
                # Dict mapping property -> value (single snak per property).
                for ref_property, ref_value in ref.items():
                    snak = self.build_mainsnak(ref_property, ref_value)
                    if snak is not None:
                        snaks.setdefault(ref_property, []).append(snak)
                continue
            else:
                raise ValidationError(
                    f"Invalid reference entry: {ref!r}",
                    field="references",
                    value=ref,
                )

            snak = self.build_mainsnak(ref_property, ref_value)
            if snak is not None:
                snaks.setdefault(ref_property, []).append(snak)

        if not snaks:
            return None
        return [{"snaks": snaks}]


def build_claim_key(
    property_id: str,
    value: Any,
    *,
    properties_map: Dict[str, str],
    unit: Optional[str] = None,
) -> Tuple[str, Any]:
    """Return (property_id, comparison_value) used for duplicate detection.

    For Quantity properties with a unit the comparison key includes the unit,
    otherwise the raw value is used. This matches the semantics expected by
    ``get_statement_id`` and ``update_unique_property``.
    """
    prop_type = properties_map.get(property_id)
    if prop_type == "Quantity" and unit:
        return property_id, f"{value}{unit}"
    return property_id, value
