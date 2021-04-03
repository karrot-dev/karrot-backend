from rest_framework import renderers
from rest_framework.utils.serializer_helpers import ReturnDict
from icalendar import Calendar, Event


class ICSCalendarRenderer(renderers.BaseRenderer):
    """renders a list of iCal VEVENT as an iCal VCALENDAR."""
    media_type = 'text/calendar'
    format = 'ics'
    charset = 'utf-8'

    def render(self, data, media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context['response']
        if response.exception:
            return response.status_text.title()

        # render lists of results as one calendar
        if isinstance(data, ReturnDict):
            results = [data]
        else:
            results = data

        calendar = Calendar()
        calendar['version'] = '2.0'
        calendar['prodid'] = '-//Karrot//EN'
        for vevent in results:
            calendar.add_component(self.render_vevent(vevent))
        return calendar.to_ical()

    def render_vevent(self, vevent):
        """renders a single event"""
        event = Event()
        for key, value in vevent.items():
            if value is not None:
                event.add(key, value)
        return event
