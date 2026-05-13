"""Regression tests for Phase 0.5b monitoring transactions list grouping."""

import pytest

from src.services.monitoring_service import MonitoringService

REQUEST_SPAN_NAMES = {
    "mcp.tools.call",
    "mcp.tools.list",
    "proxy.dynamic",
    "http.request",
    "stoa-connect.routes.fetch",
    "stoa-connect.routes.sync",
    "stoa-connect.heartbeat",
    "stoa-connect.discovery",
    "stoa-connect.sync",
    "stoa-connect.register",
    "HTTP GET",
    "HTTP POST",
}


def _span(
    trace_idx: int,
    name: str,
    *,
    span_id: str,
    parent_span_id: str = "",
    route: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    start_suffix: str = "000000000",
    duration_nanos: int = 500_000,
) -> dict:
    source: dict = {
        "traceId": f"trace-{trace_idx:02d}",
        "spanId": span_id,
        "parentSpanId": parent_span_id,
        "name": name,
        "serviceName": "stoa-gateway",
        "startTime": f"2026-05-10T12:00:{trace_idx:02d}.{start_suffix}Z",
        "durationInNanos": duration_nanos,
        "resource.attributes.stoa@deployment_mode": "edge-mcp",
        "traceGroup": "http.request" if name == "http.request" else None,
        "traceGroupFields": {
            "durationInNanos": duration_nanos if name == "http.request" else None,
            "statusCode": 1 if status_code and status_code < 400 else 2,
        },
    }
    if route is not None:
        source["span.attributes.http@route"] = route
    if method is not None:
        source["span.attributes.http@method"] = method
    if status_code is not None:
        source["span.attributes.http@status_code"] = str(status_code)
    return {"_id": span_id, "_source": source}


class FixtureOpenSearchClient:
    def __init__(self, trace_count: int):
        self.search_bodies: list[dict] = []
        self.traces: dict[str, list[dict]] = {}
        for idx in range(trace_count):
            trace_id = f"trace-{idx:02d}"
            root_id = f"root-{idx:02d}"
            specs = [
                (
                    "http.request",
                    root_id,
                    "",
                    "000000000",
                    900_000,
                    {"route": "/apis/echo-fallback/", "method": "GET", "status_code": 404},
                ),
                ("proxy.dynamic", f"proxy-{idx:02d}", root_id, "500000000", 100_000, {"status_code": 404}),
                ("policy.supervision", f"policy-{idx:02d}", root_id, "100000000", 800_000, {}),
                ("policy.quota", f"quota-{idx:02d}", f"policy-{idx:02d}", "200000000", 400_000, {}),
                ("auth.profile", f"auth-{idx:02d}", f"quota-{idx:02d}", "300000000", 100_000, {}),
            ]
            self.traces[trace_id] = [
                _span(
                    idx,
                    name,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    start_suffix=start_suffix,
                    duration_nanos=duration_nanos,
                    **attrs,
                )
                for name, span_id, parent_span_id, start_suffix, duration_nanos, attrs in specs
            ]

    def newest_trace_ids(self, limit: int | None = None) -> list[str]:
        trace_ids = sorted(self.traces, reverse=True)
        return trace_ids if limit is None else trace_ids[:limit]

    async def search(self, index: str, body: dict) -> dict:
        assert index == "otel-v1-apm-span-*"
        self.search_bodies.append(body)

        trace_id = self._term_value(body, "traceId")
        if trace_id is not None:
            return {"hits": {"hits": self.traces.get(trace_id, [])}}

        span_id = self._term_value(body, "spanId")
        if span_id is not None:
            for spans in self.traces.values():
                for hit in spans:
                    if hit["_source"]["spanId"] == span_id:
                        return {"hits": {"hits": [hit]}}
            return {"hits": {"hits": []}}

        trace_ids = self._terms_value(body, "traceId")
        if trace_ids is not None:
            hits = [
                hit
                for trace_id in trace_ids
                for hit in self.traces.get(trace_id, [])
                if hit["_source"]["name"] not in REQUEST_SPAN_NAMES
            ]
            return {"hits": {"hits": hits}}

        request_hits = self._request_hits(body)
        limit = int(body.get("size", 10))
        if "collapse" in body:
            collapsed = []
            for trace_id in self.newest_trace_ids():
                group_hits = [hit for hit in request_hits if hit["_source"]["traceId"] == trace_id]
                if not group_hits:
                    continue
                inner_hits = {"transaction_spans": {"hits": {"hits": sorted(group_hits, key=self._start_time)}}}
                collapsed.append(
                    {
                        **group_hits[0],
                        "inner_hits": inner_hits,
                    }
                )
                if len(collapsed) == limit:
                    break
            return {"hits": {"hits": collapsed}}

        return {"hits": {"hits": request_hits[:limit]}}

    def _request_hits(self, body: dict) -> list[dict]:
        route = self._route_filter(body)
        hits = [
            hit
            for trace_id in self.newest_trace_ids()
            for hit in sorted(self.traces[trace_id], key=self._start_time, reverse=True)
            if hit["_source"]["name"] in REQUEST_SPAN_NAMES
        ]
        if route is not None:
            hits = [hit for hit in hits if hit["_source"].get("span.attributes.http@route") == route]
        return hits

    def _term_value(self, body: dict, field: str) -> str | None:
        for item in self._filter_items(body):
            value = item.get("term", {}).get(field)
            if value is not None:
                return str(value)
        query = body.get("query", {})
        value = query.get("term", {}).get(field)
        return str(value) if value is not None else None

    def _terms_value(self, body: dict, field: str) -> list[str] | None:
        for item in self._filter_items(body):
            value = item.get("terms", {}).get(field)
            if value is not None:
                return [str(entry) for entry in value]
        return None

    def _route_filter(self, body: dict) -> str | None:
        for item in self._filter_items(body):
            for clause in item.get("bool", {}).get("should", []):
                route = clause.get("term", {}).get("span.attributes.http@route")
                if route is not None:
                    return str(route)
        return None

    def _filter_items(self, body: dict) -> list[dict]:
        query = body.get("query", {})
        return query.get("bool", {}).get("filter", [])

    def _start_time(self, hit: dict) -> str:
        return str(hit["_source"]["startTime"])


@pytest.mark.asyncio
async def test_list_detail_counts_are_consistent_for_same_time_window():
    client = FixtureOpenSearchClient(trace_count=12)
    service = MonitoringService(client)

    listed = await service.list_transactions_from_spans(limit=12, time_range_minutes=15)

    assert listed is not None
    assert len(listed) == 12
    assert [tx.trace_id for tx in listed] == client.newest_trace_ids(12)

    for trace_id in client.newest_trace_ids(12):
        detail = await service.get_transaction_from_spans(trace_id=trace_id)
        assert detail is not None
        assert detail.trace_id == trace_id
        assert detail.spans


@pytest.mark.asyncio
async def test_known_multi_trace_fixture_returns_all_traces_not_a_span_subset():
    client = FixtureOpenSearchClient(trace_count=30)
    service = MonitoringService(client)

    listed = await service.list_transactions_from_spans(time_range_minutes=15)

    assert listed is not None
    assert len(listed) == 30
    assert [tx.trace_id for tx in listed] == client.newest_trace_ids()
    assert len({tx.trace_id for tx in listed}) == 30


@pytest.mark.asyncio
async def test_explicit_limit_is_respected_but_default_does_not_undercount():
    client = FixtureOpenSearchClient(trace_count=30)
    service = MonitoringService(client)

    default_list = await service.list_transactions_from_spans(time_range_minutes=15)
    limited_list = await service.list_transactions_from_spans(limit=7, time_range_minutes=15)

    assert default_list is not None
    assert len(default_list) == 30
    assert limited_list is not None
    assert [tx.trace_id for tx in limited_list] == client.newest_trace_ids(7)

    list_bodies = [body for body in client.search_bodies if body.get("sort") == [{"startTime": {"order": "desc"}}]]
    assert list_bodies
    assert all(body["collapse"]["field"] == "traceId" for body in list_bodies)
