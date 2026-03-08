"""Registry of custom property pipelines. Map property name -> factory(prop_name, prop_schema)."""

from app.custom_pipelines.address import AddressPipeline
from app.custom_pipelines.coordinates import CoordinatesPipeline
from app.custom_pipelines.description import DescriptionPipeline
from app.custom_pipelines.google_maps_url import GoogleMapsUrlPipeline
from app.custom_pipelines.latitude import LatitudePipeline
from app.custom_pipelines.location_relation import LocationRelationPipeline
from app.custom_pipelines.longitude import LongitudePipeline
from app.custom_pipelines.constant_value import SourcePipeline
from app.custom_pipelines.neighborhood import NeighborhoodPipeline
from app.custom_pipelines.no_op import NoOpPipeline
from app.custom_pipelines.phone_number import PhoneNumberPipeline
from app.custom_pipelines.primary_type import PrimaryTypePipeline
from app.custom_pipelines.tags import TagsPipeline
from app.custom_pipelines.title import TitlePipeline
from app.custom_pipelines.website_url import WebsiteUrlPipeline

CUSTOM_PIPELINE_REGISTRY: dict[str, type] = {
    "Title": TitlePipeline,
    "Name": TitlePipeline,
    "Primary Type": PrimaryTypePipeline,
    "Main Type": PrimaryTypePipeline,
    "Type": PrimaryTypePipeline,
    "Description": DescriptionPipeline,
    "Notes": DescriptionPipeline,
    "Phone Number": PhoneNumberPipeline,
    "Phone": PhoneNumberPipeline,
    "Website": WebsiteUrlPipeline,
    "Website URL": WebsiteUrlPipeline,
    "URL": WebsiteUrlPipeline,
    "Google Maps": GoogleMapsUrlPipeline,
    "Maps URL": GoogleMapsUrlPipeline,
    "Address": AddressPipeline,
    "Latitude": LatitudePipeline,
    "Lat": LatitudePipeline,
    "Longitude": LongitudePipeline,
    "Lng": LongitudePipeline,
    "Long": LongitudePipeline,
    "Coordinates": CoordinatesPipeline,
    "Coords": CoordinatesPipeline,
    "Tags": TagsPipeline,
    "Neighborhood": NeighborhoodPipeline,
    "Location": LocationRelationPipeline,
    "Locations": LocationRelationPipeline,
    "Source": SourcePipeline,
    "Yelp": NoOpPipeline,
}
