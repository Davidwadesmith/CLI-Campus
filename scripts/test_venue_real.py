"""Real network integration test for VenueAdapter."""
import asyncio
import datetime

from cli_campus.adapters.venue_adapter import VenueAdapter


async def main():
    adapter = VenueAdapter()

    try:
        # 1. check_auth
        print("=== check_auth ===")
        ok = await adapter.check_auth()
        print(f"  auth: {ok}")
        assert ok, "认证失败"

        # 2. get_current_time
        print("\n=== get_current_time ===")
        now = VenueAdapter.get_current_time()
        print(f"  now: {now}")

        # 3. get_venues
        print("\n=== get_venues (羽毛球场) ===")
        venues = await adapter.get_venues("羽毛球场")
        print(f"  found {len(venues)} courts")
        for v in venues[:3]:
            print(f"    {v.number} | {v.name} | {v.campus} | cap={v.capacity}")
        assert len(venues) > 0, "未获取到场馆"

        # 4. get_time_slots
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        print(f"\n=== get_time_slots ({venues[0].name}, {tomorrow}) ===")
        slots = await adapter.get_time_slots(venues[0].venue_id, tomorrow)
        print(f"  found {len(slots)} slots")
        for s in slots:
            avail_mark = "✓" if s.available > 0 else "✗"
            print(
                f"    {avail_mark} {s.start_time}-{s.end_time} "
                f"| avail={s.available} | {s.status_text}"
            )
        assert len(slots) > 0, "未获取到时段"

        # 5. get_my_bookings
        print("\n=== get_my_bookings ===")
        bookings = await adapter.get_my_bookings()
        print(f"  found {len(bookings)} bookings")
        for b in bookings:
            print(
                f"    {b.venue_name} | {b.date} {b.start_time}-{b.end_time} "
                f"| state={b.state}"
            )

        # 6. fetch (standard adapter protocol)
        print("\n=== fetch (standard protocol) ===")
        events = await adapter.fetch(
            type_name="羽毛球场",
            date=tomorrow,
            campus="九龙湖",
        )
        print(f"  found {len(events)} events")
        for e in events[:5]:
            print(f"    [{e.category.value}] {e.title}")

        print("\n✅ All integration checks passed!")

    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        raise
    finally:
        await adapter.close()


asyncio.run(main())
