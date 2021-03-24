from django.test import TestCase
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework.response import Response
from karrot.activities.renderers import ICSCalendarRenderer


class ICSCalendarRendererTest(TestCase):
    def setUp(self):
        self.renderer = ICSCalendarRenderer()
        self.event = ReturnDict({
            'DTSTART': '20210319T170000Z',
            'DTEND': '20210319T180000Z',
            'DESCRIPTION': 'Hello\nWorld!',
            'TRANSP': 'OPAQUE'
        },
                                serializer=None)
        self.expected_output = (
            "BEGIN:VCALENDAR\r\n" + "VERSION:2.0\r\n" + "PRODID:-//Karrot//EN\r\n" + "BEGIN:VEVENT\r\n" +
            "DTSTART:20210319T170000Z\r\n" + "DTEND:20210319T180000Z\r\n" + "DESCRIPTION:Hello\\nWorld!\r\n" +
            "TRANSP:OPAQUE\r\n" + "END:VEVENT\r\n" + "END:VCALENDAR"
        )
        self.renderer_context = {'response': Response()}

    def test_render_ics_calendar(self):
        calendar = ReturnList([self.event], serializer=None)
        self.assertEqual(self.renderer.render(calendar, renderer_context=self.renderer_context), self.expected_output)

    def test_render_ics_event(self):
        self.assertEqual(
            self.renderer.render(self.event, renderer_context=self.renderer_context), self.expected_output
        )
