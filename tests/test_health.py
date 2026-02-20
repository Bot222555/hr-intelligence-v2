"""Health check endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Health endpoint returns 200 with status healthy."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
