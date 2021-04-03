from django.test import TestCase
from pytz import UTC
from datetime import datetime
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework.response import Response
from karrot.activities.renderers import ICSCalendarRenderer
from icalendar import vCalAddress, vText


class ICSCalendarRendererTest(TestCase):
    def setUp(self):
        self.renderer = ICSCalendarRenderer()
        attendee = vCalAddress('MAILTO:marysmith@example.com')
        attendee.params['cn'] = vText('Mary Smith')
        attendee.params['ROLE'] = vText('REQ-PARTICIPANT')
        self.event = ReturnDict({
            'dtstart': datetime(year=2021, month=3, day=19, hour=17, tzinfo=UTC),
            'dtend': datetime(year=2021, month=3, day=19, hour=18, tzinfo=UTC),
            'description': 'Hello\nWorld!',
            'transp': 'OPAQUE',
            'attendee': attendee,
            'toskip': None
        },
                                serializer=None)
        self.expected_output = '\r\n'.join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Karrot//EN", "BEGIN:VEVENT",
            "DTSTART;VALUE=DATE-TIME:20210319T170000Z", "DTEND;VALUE=DATE-TIME:20210319T180000Z",
            "ATTENDEE;CN=\"Mary Smith\";ROLE=REQ-PARTICIPANT:MAILTO:marysmith@example.com",
            "DESCRIPTION:Hello\\nWorld!", "TRANSP:OPAQUE", "END:VEVENT", "END:VCALENDAR"
        ])
        self.renderer_context = {'response': Response()}

    def test_render_ics_calendar(self):
        calendar = ReturnList([self.event], serializer=None)
        result = self.renderer.render(calendar, renderer_context=self.renderer_context)
        self.assertEqual(result.decode('utf-8').strip(), self.expected_output)

    def test_render_ics_event(self):
        result = self.renderer.render(self.event, renderer_context=self.renderer_context)
        self.assertEqual(result.decode('utf-8').strip(), self.expected_output)
