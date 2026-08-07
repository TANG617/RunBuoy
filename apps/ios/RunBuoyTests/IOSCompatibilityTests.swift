import XCTest
@testable import RunBuoyApp

final class IOSCompatibilityTests: XCTestCase {
    func testIOS18Through25UseMaterialFallback() {
        for majorVersion in 18...25 {
            XCTAssertEqual(
                RunBuoyVisualStyle.resolved(
                    osMajorVersion: majorVersion,
                    liquidGlassAPIsAvailable: true
                ),
                .material
            )
        }
    }

    func testLiquidGlassRequiresIOS26AndCompiledAPIs() {
        XCTAssertEqual(
            RunBuoyVisualStyle.resolved(
                osMajorVersion: 26,
                liquidGlassAPIsAvailable: false
            ),
            .material
        )
        XCTAssertEqual(
            RunBuoyVisualStyle.resolved(
                osMajorVersion: 26,
                liquidGlassAPIsAvailable: true
            ),
            .liquidGlass
        )
    }
}
