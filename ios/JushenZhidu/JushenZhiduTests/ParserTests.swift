import XCTest
@testable import JushenZhidu

final class ParserTests: XCTestCase {
    func testAtomParserExtractsPaperMetadata() throws {
        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
          <opensearch:totalResults>1</opensearch:totalResults>
          <entry>
            <id>http://arxiv.org/abs/2606.00001v1</id>
            <title>OpenVLA for Mobile Manipulation</title>
            <summary>We study vision-language-action policies for robot manipulation.</summary>
            <published>2026-06-08T12:00:00Z</published>
            <updated>2026-06-08T12:00:00Z</updated>
            <author><name>Ada Lovelace</name><arxiv:affiliation>Robot Lab</arxiv:affiliation></author>
            <arxiv:primary_category term="cs.RO" />
            <category term="cs.RO" />
            <category term="cs.AI" />
            <link href="http://arxiv.org/abs/2606.00001v1" rel="alternate" type="text/html" />
            <link href="http://arxiv.org/pdf/2606.00001v1" title="pdf" type="application/pdf" />
          </entry>
        </feed>
        """

        let page = try ArxivAtomParser().parse(Data(xml.utf8))

        XCTAssertEqual(page.totalResults, 1)
        XCTAssertEqual(page.entries.first?.arxivId, "2606.00001v1")
        XCTAssertEqual(page.entries.first?.title, "OpenVLA for Mobile Manipulation")
        XCTAssertEqual(page.entries.first?.authors, ["Ada Lovelace"])
        XCTAssertEqual(page.entries.first?.affiliations, ["Robot Lab"])
        XCTAssertEqual(page.entries.first?.primaryCategory, "cs.RO")
        XCTAssertEqual(page.entries.first?.categories, ["cs.RO", "cs.AI"])
    }
}
