import Foundation
import Translation

@main
struct Main {
    static func main() async {
        let source = Locale.Language(identifier: "zh-Hans")
        let target = Locale.Language(identifier: "en")
        let availability = LanguageAvailability()
        let status = await availability.status(from: source, to: target)
        print("status=\(status)")
        guard status == .installed else { return }
        let session = TranslationSession(installedSource: source, target: target)
        do {
            let response = try await session.translate("金融市场的实时数据太乱，噪音多、变化快。")
            print(response.targetText)
        } catch {
            fputs("\(error)\n", stderr)
        }
    }
}
