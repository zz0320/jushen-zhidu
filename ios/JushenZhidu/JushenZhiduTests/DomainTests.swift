import XCTest
@testable import JushenZhidu

final class DomainTests: XCTestCase {
    func testFetchableBatchDaysSkipFridayAndSaturday() throws {
        let thursday = try makeEasternDate(year: 2026, month: 6, day: 4, hour: 12)
        let friday = try makeEasternDate(year: 2026, month: 6, day: 5, hour: 12)
        let saturday = try makeEasternDate(year: 2026, month: 6, day: 6, hour: 12)
        let sunday = try makeEasternDate(year: 2026, month: 6, day: 7, hour: 12)

        XCTAssertTrue(ArxivBatchCalendar.isFetchableBatchDay(thursday))
        XCTAssertFalse(ArxivBatchCalendar.isFetchableBatchDay(friday))
        XCTAssertFalse(ArxivBatchCalendar.isFetchableBatchDay(saturday))
        XCTAssertTrue(ArxivBatchCalendar.isFetchableBatchDay(sunday))
    }

    func testPreviousAndNextFetchableBatchDays() throws {
        let thursday = try makeEasternDate(year: 2026, month: 6, day: 4, hour: 12)
        let sunday = try makeEasternDate(year: 2026, month: 6, day: 7, hour: 12)

        XCTAssertEqual(ArxivBatchCalendar.dayString(ArxivBatchCalendar.nextFetchableBatchDay(after: thursday)), "2026-06-07")
        XCTAssertEqual(ArxivBatchCalendar.dayString(ArxivBatchCalendar.previousFetchableBatchDay(before: sunday)), "2026-06-04")
    }

    func testBatchSubmittedDateQueryUsesUTCWindows() throws {
        let monday = try makeEasternDate(year: 2026, month: 6, day: 8, hour: 12)
        let query = ArxivBatchCalendar.submittedDateQuery(for: monday)

        XCTAssertTrue(query.contains("submittedDate:"))
        XCTAssertTrue(query.contains("TO"))
        XCTAssertTrue(query.contains("20260605"))
    }

    private func makeEasternDate(year: Int, month: Int, day: Int, hour: Int) throws -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = hour
        components.minute = 0
        return try XCTUnwrap(calendar.date(from: components))
    }
}
