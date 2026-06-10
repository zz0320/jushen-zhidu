import XCTest

final class JushenZhiduUITests: XCTestCase {
    func testInitialTabsAndSettingsScreenRender() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["论文森林"].waitForExistence(timeout: 5))
        app.tabBars.buttons["设置"].tap()
        XCTAssertTrue(app.staticTexts["独立 iOS 工作台"].waitForExistence(timeout: 5))
    }
}
