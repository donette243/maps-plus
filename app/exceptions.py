class MapsPlusError(Exception):
    pass


class PlaceNotFoundError(MapsPlusError):
    pass


class RoutingUnavailableError(MapsPlusError):
    pass
