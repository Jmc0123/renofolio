"""Local AI-generated illustrative previews for fictional demo projects."""

SAMPLE_PHOTOS = {
    "Kitchen": "/static/sample-projects/kitchen.png",
    "Living Room": "/static/sample-projects/living-room.png",
    "Bedroom": "/static/sample-projects/bedroom.png",
    "Bathroom": "/static/sample-projects/bathroom.png",
    "Home Office": "/static/sample-projects/home-office.png",
    "Dining Room": "/static/sample-projects/dining-room.png",
}


# Returns the sample photo for a category's room type, such as kitchen or bedroom.
def photo_for_category(category_name):
    name = (category_name or "").strip().casefold()
    for room, url in SAMPLE_PHOTOS.items():
        if name == room.casefold() or name.endswith(" " + room.casefold()):
            return url
    return None
