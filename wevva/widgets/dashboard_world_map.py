"""Dashboard interactions over the shared full-world map."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widgets import Static
from wevva_warnings import CanonicalTropicalSystem, TropicalSystem

from wevva.config import location_key, location_label
from wevva.geography import representative_polygon_point
from wevva.location_metadata import LocationMetadata
from wevva.messages import (
    DashboardPlacePressed,
    DashboardTropicalActivated,
)
from wevva.services.tropical import (
    canonical_tropical_anchor,
    sort_canonical_tropical_systems_by_severity,
)
from wevva.services.alert_bulletin import BulletinAlert
from wevva.services.country_alerts import country_alert_identity
from wevva.widgets.geographic_scope import GeographicFrame
from wevva.widgets.map_callouts import DirectionalCalloutCandidate
from wevva.widgets.tropical_systems import (
    build_canonical_tropical_label,
    canonical_storm_key,
)
from wevva.widgets.weather_alerts import alert_condition_name, alert_severity_color
from wevva.widgets.world_locations_map import WorldLocationLabel, WorldLocationsMap


class DashboardLocationLabel(WorldLocationLabel):
    """Location callout whose primary action is owned by Dashboard."""

    BINDINGS = [
        Binding('enter', 'select_location', 'Select', show=False),
        Binding('space', 'select_location', 'Select', show=False),
    ]

    DEFAULT_CSS = """
    DashboardLocationLabel.active-place {
        text-style: bold;
    }

    DashboardLocationLabel.selected-place,
    DashboardLocationLabel.selected-place:hover,
    DashboardLocationLabel.selected-place:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self, location: LocationMetadata) -> None:
        super().__init__(location)
        self.tooltip = location_label(location)

    def action_select_location(self) -> None:
        """Use one message path for click, Enter, and Space."""

        self.post_message(DashboardPlacePressed(location=self.location))

class DashboardTropicalLabel(Static, can_focus=True):
    """One canonical storm anchored to an exact source observation."""

    BINDINGS = [
        Binding('enter', 'activate', 'Select', show=False),
        Binding('space', 'activate', 'Select', show=False),
    ]

    DEFAULT_CSS = """
    DashboardTropicalLabel {
        position: absolute;
        layer: labels;
        width: auto;
        height: 1;
        min-width: 1;
        background: $background;
        pointer: pointer;
    }

    DashboardTropicalLabel:hover,
    DashboardTropicalLabel:focus {
        text-style: reverse;
    }

    DashboardTropicalLabel.selected-tropical,
    DashboardTropicalLabel.selected-tropical:hover,
    DashboardTropicalLabel.selected-tropical:focus {
        text-style: reverse;
    }
    """

    def __init__(
        self,
        system: CanonicalTropicalSystem,
        observation: TropicalSystem,
    ) -> None:
        super().__init__('', markup=False)
        self.system = system
        self.observation = observation
        self._body = Text()
        self._marker_on_right = False
        self.label_text = ''

    @property
    def tropical_key(self) -> str:
        return canonical_storm_key(self.system)

    def update_system(
        self,
        system: CanonicalTropicalSystem,
        observation: TropicalSystem,
    ) -> None:
        self.system = system
        self.observation = observation
        self._body = build_canonical_tropical_label(
            system,
            self.app.theme_variables,
        )
        self.tooltip = _tropical_tooltip(
            system,
            observation,
            self.app.theme_variables,
        )
        self.set_marker_on_right(self._marker_on_right)

    def set_marker_on_right(self, marker_on_right: bool) -> None:
        self._marker_on_right = marker_on_right
        label = Text()
        theme = self.app.theme_variables
        accent = theme.get('accent') or theme.get('text-accent')
        if marker_on_right:
            label.append_text(self._body)
            label.append(' ★', style=accent)
        else:
            label.append('★ ', style=accent)
            label.append_text(self._body)
        self.label_text = label.plain
        self.update(label)

    def action_activate(self) -> None:
        self.post_message(
            DashboardTropicalActivated(
                system=self.system,
                observation=self.observation,
            )
        )

    def on_click(self, event: Click) -> None:
        event.stop()
        self.focus()
        self.action_activate()


class DashboardAlertMarker(Static, can_focus=True):
    """The dashboard's steady selected or transient-preview alert marker."""

    class Activated(Message):
        def __init__(self, row: BulletinAlert) -> None:
            super().__init__()
            self.row = row

    BINDINGS = [
        Binding('enter', 'activate', 'Open alert', show=False),
        Binding('space', 'activate', 'Open alert', show=False),
    ]

    DEFAULT_CSS = """
    DashboardAlertMarker {
        position: absolute;
        layer: alert-marker;
        width: 1;
        height: 1;
        min-width: 1;
        background: $background;
        text-style: bold reverse;
        pointer: pointer;
    }

    DashboardAlertMarker:hover,
    DashboardAlertMarker:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self) -> None:
        super().__init__('!', markup=False, id='dashboard-alert-marker')
        self.row: BulletinAlert | None = None
        self.preview = False

    def show_alert(self, row: BulletinAlert, *, preview: bool) -> None:
        self.row = row
        self.preview = preview
        self.set_class(preview, 'preview')
        self.styles.color = alert_severity_color(
            self.app.theme_variables,
            row.alert,
        )
        self.tooltip = alert_condition_name(row.alert)

    def action_activate(self) -> None:
        if self.row is not None and not self.preview:
            self.post_message(self.Activated(self.row))

    def on_click(self, event: Click) -> None:
        event.stop()
        if not self.preview:
            self.focus()
            self.action_activate()


class DashboardIncomingAlertMarker(Static):
    """One temporary marker for newly discovered alerts in a map cell."""

    DEFAULT_CSS = """
    DashboardIncomingAlertMarker {
        position: absolute;
        layer: incoming-alerts;
        width: 1;
        height: 1;
        min-width: 1;
        background: $background;
        text-style: bold reverse;
    }

    DashboardIncomingAlertMarker.pulse {
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__('!', markup=False)
        self.row: BulletinAlert | None = None
        self.count = 0

    def show_alert(self, row: BulletinAlert, count: int) -> None:
        self.row = row
        self.count = count
        self.styles.color = alert_severity_color(
            self.app.theme_variables,
            row.alert,
        )
        condition = alert_condition_name(row.alert)
        self.tooltip = (
            f'{count} new alerts · {condition}' if count > 1 else condition
        )


class DashboardWorldMap(WorldLocationsMap):
    """One projection containing location and canonical-storm callouts."""

    DEFAULT_CSS = """
    DashboardWorldMap {
        layers: map labels alert-marker incoming-alerts;
    }
    """

    def __init__(
        self,
        *args,
        active_location: LocationMetadata | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = 'World Weather'
        self._active_location_key = (
            location_key(active_location) if active_location is not None else None
        )
        self._selected_location_key: str | None = None
        self._tropical_systems: list[CanonicalTropicalSystem] = []
        self._tropical_labels: dict[str, DashboardTropicalLabel] = {}
        self._selected_tropical_key: str | None = None
        self._selected_alert: BulletinAlert | None = None
        self._preview_alert: BulletinAlert | None = None
        self._alert_marker_widget: DashboardAlertMarker | None = None
        self._incoming_alerts: tuple[BulletinAlert, ...] = ()
        self._incoming_alert_markers: list[DashboardIncomingAlertMarker] = []
        self._incoming_alert_pulse_task: asyncio.Task[None] | None = None
        self._incoming_alert_pulse_generation = 0

    def compose(self) -> ComposeResult:
        yield from super().compose()
        marker = DashboardAlertMarker()
        self._alert_marker_widget = marker
        marker.display = False
        yield marker

    @property
    def selected_location_key(self) -> str | None:
        return self._selected_location_key

    @property
    def selected_tropical_key(self) -> str | None:
        return self._selected_tropical_key

    @property
    def alert_marker(self) -> DashboardAlertMarker:
        if self._alert_marker_widget is None:
            self._alert_marker_widget = self.query_one(
                '#dashboard-alert-marker',
                DashboardAlertMarker,
            )
        return self._alert_marker_widget

    def set_selected_alert(
        self,
        row: BulletinAlert | None,
    ) -> None:
        """Replace the one persistent, steady alert marker."""

        changed = _bulletin_identity(row) != _bulletin_identity(self._selected_alert)
        self._selected_alert = row
        self._preview_alert = None
        self._update_alert_marker()
        if changed:
            self._schedule_reflow()

    def flash_new_alerts(self, rows: Sequence[BulletinAlert]) -> None:
        """Flash every geographically usable alert in one new bulletin batch."""

        self._cancel_incoming_alert_pulse()
        self._incoming_alerts = tuple(
            row
            for row in rows
            if row.is_new
            and representative_polygon_point(row.alert.geometry) is not None
        )
        self._sync_incoming_alert_markers()
        if not self._incoming_alerts:
            return
        generation = self._incoming_alert_pulse_generation
        self._incoming_alert_pulse_task = asyncio.create_task(
            self._pulse_incoming_alerts(generation)
        )

    def set_alert_preview(self, row: BulletinAlert | None) -> None:
        """Temporarily replace the marker without committing map selection."""

        if _bulletin_identity(row) == _bulletin_identity(self._selected_alert):
            row = None
        if _bulletin_identity(row) == _bulletin_identity(self._preview_alert):
            return
        self._preview_alert = row
        self._update_alert_marker()

    def pause_alert_marker(self) -> None:
        """Stop transient marker behavior while Dashboard is not current."""

        self._preview_alert = None
        self._cancel_incoming_alert_pulse()
        if self.is_mounted:
            self._update_alert_marker()

    def set_active_location(self, location: LocationMetadata | None) -> None:
        """Update the active-place emphasis without changing selection."""

        key = (
            location_key(location) if location is not None else None
        )
        if key == self._active_location_key:
            return
        self._active_location_key = key
        self._apply_label_state()
        self._schedule_reflow()

    def set_selected_location(self, location: LocationMetadata | None) -> None:
        """Apply persistent dashboard selection without moving callouts."""

        key = (
            location_key(location) if location is not None else None
        )
        if key == self._selected_location_key:
            return
        self._selected_location_key = key
        self._apply_label_state()

    def set_tropical_systems(
        self,
        systems: Sequence[CanonicalTropicalSystem],
        *,
        force: bool = False,
    ) -> None:
        """Replace canonical storm inputs while retaining matching widgets."""

        sorted_systems = sort_canonical_tropical_systems_by_severity(
            systems
        )
        if not force and sorted_systems == self._tropical_systems:
            return
        self._tropical_systems = sorted_systems
        if self.is_mounted:
            self._sync_tropical_label_widgets()
            self._apply_label_state()
            self._schedule_reflow()

    def set_selected_tropical(
        self,
        system: CanonicalTropicalSystem | None,
    ) -> None:
        key = (
            canonical_storm_key(system) if system is not None else None
        )
        if key == self._selected_tropical_key:
            return
        self._selected_tropical_key = key
        self._apply_label_state()
        self._schedule_reflow()

    def focus_preferred_feature(self) -> bool:
        """Restore storm/place selection, then the active weather location."""

        if self._selected_tropical_key is not None:
            label = self._tropical_labels.get(self._selected_tropical_key)
            if label is not None and label.display:
                label.focus()
                return True
        for key in (self._selected_location_key, self._active_location_key):
            if key is None:
                continue
            label = self._labels.get(key)
            if label is not None and label.display:
                label.focus()
                return True
        return self.focus_relative(1)

    def focus_preferred_location(self) -> bool:
        """Compatibility name retained for the initial Dashboard slice."""

        return self.focus_preferred_feature()

    def focus_relative(self, direction: int) -> bool:
        labels = self._callout_labels()
        visible = [
            labels[key]
            for key in self._placements
            if key in labels and labels[key].display
        ]
        if not visible:
            return False
        focused = self.app.focused
        if focused in visible:
            index = visible.index(focused)
            target = visible[(index + (1 if direction >= 0 else -1)) % len(visible)]
        else:
            target = visible[0 if direction >= 0 else -1]
        target.focus()
        return True

    def _make_location_label(
        self,
        location: LocationMetadata,
    ) -> DashboardLocationLabel:
        return DashboardLocationLabel(location)

    def _sync_label_widgets(self) -> None:
        super()._sync_label_widgets()
        self._sync_tropical_label_widgets()
        self._apply_label_state()

    def _reflow(self) -> None:
        super()._reflow()
        self._position_alert_marker()
        self._sync_incoming_alert_markers()

    def _update_alert_marker(self) -> None:
        if not self.is_mounted:
            return
        marker = self.alert_marker
        row = self._preview_alert or self._selected_alert
        point = (
            representative_polygon_point(row.alert.geometry)
            if row is not None
            else None
        )
        if row is None or point is None:
            marker.display = False
            marker.row = None
            return
        marker.show_alert(row, preview=row is self._preview_alert)
        marker.display = True
        self._position_alert_marker(point)

    def _position_alert_marker(
        self,
        point: tuple[float, float] | None = None,
    ) -> None:
        if not self.is_mounted or not self.alert_marker.display:
            return
        row = self.alert_marker.row
        if point is None and row is not None:
            point = representative_polygon_point(row.alert.geometry)
        frame = self._current_frame
        if point is None or frame is None:
            self.alert_marker.display = False
            return
        longitude, latitude = point
        column, map_row = frame.canvas.cell_position(
            frame.canvas.viewport.project(longitude, latitude)
        )
        self.alert_marker.styles.offset = (column, map_row)

    def _sync_incoming_alert_markers(self) -> None:
        frame = self._current_frame
        if not self.is_mounted or frame is None:
            return
        grouped: dict[tuple[int, int], list[BulletinAlert]] = {}
        for row in self._incoming_alerts:
            point = representative_polygon_point(row.alert.geometry)
            if point is None:
                continue
            longitude, latitude = point
            cell = frame.canvas.cell_position(
                frame.canvas.viewport.project(longitude, latitude)
            )
            grouped.setdefault(cell, []).append(row)

        while len(self._incoming_alert_markers) < len(grouped):
            marker = DashboardIncomingAlertMarker()
            marker.display = False
            self._incoming_alert_markers.append(marker)
            self.mount(marker)
        for marker in self._incoming_alert_markers:
            marker.display = False
        for marker, (cell, rows) in zip(
            self._incoming_alert_markers,
            grouped.items(),
        ):
            row = max(rows, key=_alert_severity_rank)
            marker.show_alert(row, len(rows))
            marker.styles.offset = cell
            marker.display = True

    async def _pulse_incoming_alerts(self, generation: int) -> None:
        try:
            for phase in range(40):
                for marker in self._incoming_alert_markers:
                    if marker.display:
                        marker.set_class(phase % 2 == 0, 'pulse')
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise
        finally:
            if generation == self._incoming_alert_pulse_generation:
                self._incoming_alerts = ()
                for marker in self._incoming_alert_markers:
                    marker.remove_class('pulse')
                    marker.display = False
                if self._incoming_alert_pulse_task is asyncio.current_task():
                    self._incoming_alert_pulse_task = None

    def _cancel_incoming_alert_pulse(self) -> None:
        self._incoming_alert_pulse_generation += 1
        if self._incoming_alert_pulse_task is not None:
            self._incoming_alert_pulse_task.cancel()
            self._incoming_alert_pulse_task = None
        self._incoming_alerts = ()
        for marker in self._incoming_alert_markers:
            marker.remove_class('pulse')
            marker.display = False

    def on_unmount(self) -> None:
        self._cancel_incoming_alert_pulse()

    def _sync_tropical_label_widgets(self) -> None:
        anchored: dict[
            str,
            tuple[CanonicalTropicalSystem, TropicalSystem],
        ] = {}
        for system in self._tropical_systems:
            anchor = canonical_tropical_anchor(system)
            if anchor is not None:
                anchored.setdefault(canonical_storm_key(system), (system, anchor))

        for key in tuple(self._tropical_labels):
            if key not in anchored:
                self._tropical_labels.pop(key).remove()
        for key, (system, anchor) in anchored.items():
            label = self._tropical_labels.get(key)
            if label is None:
                label = DashboardTropicalLabel(system, anchor)
                self._tropical_labels[key] = label
                self.mount(label)
            label.update_system(system, anchor)

    def _apply_label_state(self) -> None:
        for key, label in self._labels.items():
            label.set_class(key == self._active_location_key, 'active-place')
            label.set_class(key == self._selected_location_key, 'selected-place')
        for key, label in self._tropical_labels.items():
            label.set_class(
                key == self._selected_tropical_key,
                'selected-tropical',
            )

    def _ordered_locations(self) -> Sequence[LocationMetadata]:
        indexed = list(enumerate(self._locations))

        def priority(item: tuple[int, LocationMetadata]) -> tuple[int, int]:
            index, location = item
            key = location_key(location)
            if key == self._active_location_key:
                return 0, index
            return 1, index

        return [location for _, location in sorted(indexed, key=priority)]

    def _callout_candidates(
        self,
        frame: GeographicFrame,
    ) -> list[DirectionalCalloutCandidate[str]]:
        location_candidates = super()._callout_candidates(frame)
        marker_cell = self._selected_alert_marker_cell(frame)
        if marker_cell is not None:
            location_candidates = [
                replace(
                    candidate,
                    preferred_avoidance=(
                        candidate.preferred_avoidance | {marker_cell}
                    ),
                )
                for candidate in location_candidates
            ]
        by_key = {candidate.key: candidate for candidate in location_candidates}
        active_location = by_key.pop(self._active_location_key, None)

        tropical_candidates: list[DirectionalCalloutCandidate[str]] = []
        for system in self._tropical_systems:
            key = canonical_storm_key(system)
            label = self._tropical_labels.get(key)
            if label is None:
                continue
            observation = label.observation
            point = frame.canvas.viewport.project(
                float(observation.center_lon),
                float(observation.center_lat),
            )
            tropical_candidates.append(
                DirectionalCalloutCandidate(
                    key=_tropical_callout_key(key),
                    anchor=frame.canvas.cell_position(point),
                    width=cell_len(label.label_text),
                )
            )
        selected_tropical = next(
            (
                candidate
                for candidate in tropical_candidates
                if candidate.key
                == _tropical_callout_key(self._selected_tropical_key)
            ),
            None,
        )
        if selected_tropical is not None:
            tropical_candidates.remove(selected_tropical)

        ordered: list[DirectionalCalloutCandidate[str]] = []
        if selected_tropical is not None:
            ordered.append(selected_tropical)
        if active_location is not None:
            ordered.append(active_location)
        ordered.extend(tropical_candidates)
        ordered.extend(by_key.values())
        return ordered

    def _selected_alert_marker_cell(
        self,
        frame: GeographicFrame,
    ) -> tuple[int, int] | None:
        row = self._selected_alert
        point = (
            representative_polygon_point(row.alert.geometry)
            if row is not None
            else None
        )
        if point is None:
            return None
        longitude, latitude = point
        return frame.canvas.cell_position(
            frame.canvas.viewport.project(longitude, latitude)
        )

    def _callout_labels(self):
        labels = dict(self._labels)
        labels.update(
            {
                _tropical_callout_key(key): label
                for key, label in self._tropical_labels.items()
            }
        )
        return labels

def _tropical_callout_key(key: str | None) -> str:
    return f'tropical:{key or ""}'


def _bulletin_identity(row: BulletinAlert | None) -> tuple[str, str] | None:
    return None if row is None else country_alert_identity(row.alert)


def _alert_severity_rank(row: BulletinAlert) -> int:
    severity = (row.alert.severity or '').strip().casefold()
    return {
        'extreme': 4,
        'red': 4,
        'severe': 3,
        'orange': 3,
        'amber': 3,
        'moderate': 2,
        'yellow': 2,
        'minor': 1,
        'green': 1,
    }.get(severity, 0)


def _tropical_tooltip(
    system: CanonicalTropicalSystem,
    observation: TropicalSystem,
    theme: dict[str, str],
) -> Text:
    text = build_canonical_tropical_label(system, theme)
    if observation.movement:
        text.append('\n')
        text.append('Movement', style='dim')
        text.append(f' {observation.movement.strip()}')
    if observation.max_wind:
        text.append('\n')
        text.append('Wind', style='dim')
        text.append(f' {observation.max_wind.strip()}')
    return text


__all__ = [
    'DashboardLocationLabel',
    'DashboardAlertMarker',
    'DashboardIncomingAlertMarker',
    'DashboardTropicalLabel',
    'DashboardWorldMap',
]
