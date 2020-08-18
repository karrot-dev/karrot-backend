-- History.objects.filter(typus=HistoryTypus.ACTIVITY_DONE).values('place').annotate(foo=C
--     ...: ount('activity')).order_by('place__name')

SELECT "history_history"."place_id", COUNT("history_history"."activity_id") AS "foo"
FROM "history_history"
         LEFT OUTER JOIN "places_place" ON ("history_history"."place_id" = "places_place"."id")
WHERE "history_history"."typus" = 13
GROUP BY "history_history"."place_id", "places_place"."name"
ORDER BY "places_place"."name" ASC;


-- History.objects.filter(typus=HistoryTypus.ACTIVITY_DONE).annotate(foo=Count('activity')
--     ...: ).order_by('place__name').values('place')

SELECT "history_history"."place_id"
FROM "history_history"
         LEFT OUTER JOIN "places_place" ON ("history_history"."place_id" = "places_place"."id")
WHERE "history_history"."typus" = 13
GROUP BY "history_history"."id", "places_place"."name"
ORDER BY "places_place"."name" ASC;
