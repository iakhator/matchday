from typing import List

from app.connectors.base import Connector
from app.connectors.football_data_org import FootballDataOrgConnector

# Ordered list, primary first. When a second connector is added (e.g.
# OpenLigaDB as a free fallback), append it here - the sync service will
# try each in order and move on to the next if one fails or returns
# nothing, so a single upstream outage never takes the gateway down.
_connectors: List[Connector] = []


def get_connectors() -> List[Connector]:
    global _connectors
    if not _connectors:
        _connectors = [FootballDataOrgConnector()]
    return _connectors
