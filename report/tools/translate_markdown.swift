import Foundation
import Translation

struct Unit {
    let id: String
    let line: Int
    let prefix: String
    let suffix: String
}

func containsHan(_ text: String) -> Bool {
    text.unicodeScalars.contains { scalar in
        (0x3400...0x4DBF).contains(scalar.value) || (0x4E00...0x9FFF).contains(scalar.value)
    }
}

func protectedAttributedString(_ input: String) -> AttributedString {
    let patterns = [
        #"`[^`]+`"#,
        #"\\\([^)]*\\\)"#,
        #"https?://[^\s>)]+"#,
        #"\[[0-9]+(?:\s*,\s*p\.\s*[0-9]+)?\]"#,
        #"\b(?:MarketStream|FactorSnapshot|MarketEvent|AtomicEvent|DetectionResult|EventQualityGate|Kafka|TimescaleDB|Streamlit|Alpaca|IEX|SPY|QQQ|CEP|F1|Precision|Recall|SHA-256|JSONL|WebSocket|SIP|EWMA|LSTM-AE)\b"#
    ]
    var ranges: [(Int, Int)] = []
    for pattern in patterns {
        let regex = try! NSRegularExpression(pattern: pattern)
        let full = NSRange(input.startIndex..<input.endIndex, in: input)
        for match in regex.matches(in: input, range: full) {
            guard let swiftRange = Range(match.range, in: input) else { continue }
            let lo = input.distance(from: input.startIndex, to: swiftRange.lowerBound)
            let hi = input.distance(from: input.startIndex, to: swiftRange.upperBound)
            if !ranges.contains(where: { max($0.0, lo) < min($0.1, hi) }) {
                ranges.append((lo, hi))
            }
        }
    }
    var attributed = AttributedString(input)
    for (lo, hi) in ranges.sorted(by: { $0.0 > $1.0 }) {
        let lower = attributed.characters.index(attributed.startIndex, offsetBy: lo)
        let upper = attributed.characters.index(attributed.startIndex, offsetBy: hi)
        attributed[lower..<upper].translation.skipsTranslation = true
    }
    return attributed
}

@main
struct Main {
    static func main() async throws {
        guard CommandLine.arguments.count == 3 else {
            fputs("usage: translate_markdown INPUT.md OUTPUT.md\n", stderr)
            exit(2)
        }
        let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
        let sourceText = try String(contentsOf: inputURL, encoding: .utf8)
        var lines = sourceText.components(separatedBy: .newlines)
        var units: [Unit] = []
        var requests: [TranslationSession.Request] = []
        var inMath = false
        var inFence = false

        for index in lines.indices {
            let line = lines[index]
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") { inFence.toggle(); continue }
            if trimmed == "$$" || trimmed == "\\[" || trimmed == "\\]" {
                inMath.toggle(); continue
            }
            if inFence || inMath || trimmed.isEmpty || trimmed == "---" || trimmed.contains("| ---") || !containsHan(line) {
                continue
            }

            if trimmed.hasPrefix("|") {
                var cells = line.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
                for cellIndex in cells.indices where containsHan(cells[cellIndex]) {
                    let original = cells[cellIndex]
                    let lead = String(original.prefix { $0 == " " })
                    let trail = String(original.reversed().prefix { $0 == " " }.reversed())
                    let core = original.trimmingCharacters(in: .whitespaces)
                    let id = "\(index):cell:\(cellIndex)"
                    units.append(Unit(id: id, line: index, prefix: lead, suffix: trail))
                    requests.append(.init(sourceText: protectedAttributedString(core), clientIdentifier: id))
                }
                continue
            }

            var prefix = ""
            var core = line
            if let match = line.range(of: #"^(#{1,6}\s+|\s*(?:[-*+] |\d+\. )|(?:Table|Figure)\s+\d+\.\s*)"#, options: .regularExpression) {
                prefix = String(line[match])
                core = String(line[match.upperBound...])
            }
            if let image = core.range(of: #"^!\[([^]]*)\]\(([^)]*)\)$"#, options: .regularExpression) {
                let whole = String(core[image])
                if let close = whole.firstIndex(of: "]"), let open = whole.firstIndex(of: "[") {
                    let alt = String(whole[whole.index(after: open)..<close])
                    let path = String(whole[whole.index(close, offsetBy: 2)..<whole.index(before: whole.endIndex)])
                    let id = "\(index):image"
                    units.append(Unit(id: id, line: index, prefix: prefix + "![", suffix: "](\(path))"))
                    requests.append(.init(sourceText: protectedAttributedString(alt), clientIdentifier: id))
                    continue
                }
            }
            let id = "\(index):line"
            units.append(Unit(id: id, line: index, prefix: prefix, suffix: ""))
            requests.append(.init(sourceText: protectedAttributedString(core), clientIdentifier: id))
        }

        let source = Locale.Language(identifier: "zh-Hans")
        let target = Locale.Language(identifier: "en")
        let availability = LanguageAvailability()
        guard await availability.status(from: source, to: target) == .installed else {
            throw NSError(domain: "translate_markdown", code: 1, userInfo: [NSLocalizedDescriptionKey: "Chinese-English language pack is not installed"])
        }
        let session = TranslationSession(installedSource: source, target: target, preferredStrategy: .highFidelity)
        var translated: [String: String] = [:]
        let batchSize = 40
        var start = 0
        while start < requests.count {
            let end = min(start + batchSize, requests.count)
            let responses = try await session.translations(from: Array(requests[start..<end]))
            for response in responses {
                if let id = response.clientIdentifier {
                    translated[id] = response.attributedTargetText.map { String($0.characters) } ?? response.targetText
                }
            }
            start = end
        }

        var tableCells: [Int: [(Int, String)]] = [:]
        for unit in units {
            guard let value = translated[unit.id] else { continue }
            let final = unit.prefix + value + unit.suffix
            if unit.id.contains(":cell:") {
                let parts = unit.id.split(separator: ":")
                let cell = Int(parts[2])!
                tableCells[unit.line, default: []].append((cell, final))
            } else {
                lines[unit.line] = final
            }
        }
        for (lineIndex, replacements) in tableCells {
            var cells = lines[lineIndex].split(separator: "|", omittingEmptySubsequences: false).map(String.init)
            for (cell, value) in replacements { cells[cell] = value }
            lines[lineIndex] = cells.joined(separator: "|")
        }

        // Keep the deliberately simple paper title and use an English reference heading.
        lines = lines.map { $0 == "# 参考文献" ? "# References" : $0 }
        try lines.joined(separator: "\n").write(to: outputURL, atomically: true, encoding: .utf8)
    }
}
