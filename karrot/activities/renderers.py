from rest_framework import renderers
from rest_framework.utils.serializer_helpers import ReturnDict


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

        lines = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//Karrot//EN',
        ]
        lines += [self.render_vevent(vevent) for vevent in results]
        lines += ['END:VCALENDAR']
        # CRLF is required by the specs
        return '\r\n'.join(lines)

    def render_vevent(self, vevent):
        """renders a single event"""
        lines = [
            'BEGIN:VEVENT',
        ]
        lines += [
            '{}:{}'.format(key.upper().replace('_', '-'), value.replace('\n', '\\n')) for key, value in vevent.items()
        ]
        lines += [
            'END:VEVENT',
        ]
        return '\r\n'.join(lines)
