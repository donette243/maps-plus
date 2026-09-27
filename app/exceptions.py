class MapsPlusError(Exception):
    pass


class PlaceNotFoundError(MapsPlusError):
    pass


class RouteNotFoundError(MapsPlusError):
    pass


class ProviderUnavailableError(MapsPlusError):
    pass


class ProviderQuotaExceededError(
    ProviderUnavailableError
):
    pass


class InvalidProviderResponseError(
    ProviderUnavailableError
):
    pass


class ConfigurationError(MapsPlusError):
    pass


class RoutingUnavailableError(
    ProviderUnavailableError
):
    pass