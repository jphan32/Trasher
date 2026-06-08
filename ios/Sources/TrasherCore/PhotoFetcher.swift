// 사진 HTTP 다운로드. docs/protocol.md §"사진 채널", §3.3.
// Pi가 BLE로 PhotoReady{cycle, path}를 보내면 iPad가 DeviceInfo의 ip:port와 합쳐 GET.

import Foundation

public enum PhotoFetchError: Error, Equatable {
    case badURL
    case httpStatus(Int)
}

/// DeviceInfo + PhotoReady → 사진 URL. `http://{ip}:{port}{path}`.
public func photoURL(device: DeviceInfo, photo: PhotoReady) -> URL? {
    URL(string: "http://\(device.ip):\(device.port)\(photo.path)")
}

/// 사진 다운로드 추상화. 코디네이터는 이 뒤에서 동작(테스트 시 Mock).
public protocol PhotoFetcher: Sendable {
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data
}

/// URLSession 기반 실제 구현.
public struct URLSessionPhotoFetcher: PhotoFetcher {
    private let session: URLSession
    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data {
        guard let url = photoURL(device: device, photo: photo) else {
            throw PhotoFetchError.badURL
        }
        let (data, response) = try await session.data(from: url)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw PhotoFetchError.httpStatus(http.statusCode)
        }
        return data
    }
}
