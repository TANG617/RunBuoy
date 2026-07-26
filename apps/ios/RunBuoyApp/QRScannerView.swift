import AVFoundation
import SwiftUI
import UIKit

struct QRScannerView: UIViewControllerRepresentable {
    let onCode: (String) -> Void
    let onFailure: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onCode: onCode, onFailure: onFailure)
    }

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.coordinator = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}

    final class Coordinator: NSObject, AVCaptureMetadataOutputObjectsDelegate {
        private let onCode: (String) -> Void
        private let onFailure: (String) -> Void
        private var delivered = false

        init(onCode: @escaping (String) -> Void, onFailure: @escaping (String) -> Void) {
            self.onCode = onCode
            self.onFailure = onFailure
        }

        func metadataOutput(
            _ output: AVCaptureMetadataOutput,
            didOutput metadataObjects: [AVMetadataObject],
            from connection: AVCaptureConnection
        ) {
            guard !delivered,
                  let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
                  object.type == .qr,
                  let value = object.stringValue
            else { return }
            delivered = true
            onCode(value)
        }

        func fail(_ message: String) {
            onFailure(message)
        }
    }
}

final class ScannerViewController: UIViewController {
    weak var coordinator: QRScannerView.Coordinator?
    private let captureSession = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureCapture()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        guard !captureSession.isRunning else { return }
        DispatchQueue.global(qos: .userInitiated).async { [captureSession] in
            captureSession.startRunning()
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        guard captureSession.isRunning else { return }
        DispatchQueue.global(qos: .userInitiated).async { [captureSession] in
            captureSession.stopRunning()
        }
    }

    private func configureCapture() {
#if targetEnvironment(simulator)
        coordinator?.fail(String(localized: "pairing.camera_unavailable"))
#else
        guard let camera = AVCaptureDevice.default(for: .video) else {
            coordinator?.fail(String(localized: "pairing.camera_unavailable"))
            return
        }
        do {
            let input = try AVCaptureDeviceInput(device: camera)
            guard captureSession.canAddInput(input) else {
                coordinator?.fail(String(localized: "pairing.camera_unavailable"))
                return
            }
            captureSession.addInput(input)
            let metadata = AVCaptureMetadataOutput()
            guard captureSession.canAddOutput(metadata) else {
                coordinator?.fail(String(localized: "pairing.camera_unavailable"))
                return
            }
            captureSession.addOutput(metadata)
            metadata.setMetadataObjectsDelegate(coordinator, queue: .main)
            metadata.metadataObjectTypes = [.qr]

            let layer = AVCaptureVideoPreviewLayer(session: captureSession)
            layer.videoGravity = .resizeAspectFill
            view.layer.addSublayer(layer)
            previewLayer = layer
        } catch {
            coordinator?.fail(String(localized: "pairing.camera_unavailable"))
        }
#endif
    }
}

struct ScannerSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onCode: (String) -> Void
    @State private var failureMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                QRScannerView(
                    onCode: {
                        onCode($0)
                        dismiss()
                    },
                    onFailure: { failureMessage = $0 }
                )
                if let failureMessage {
                    ContentUnavailableView {
                        Label("pairing.camera_unavailable_title", systemImage: "camera.fill")
                    } description: {
                        Text(failureMessage)
                    }
                    .background(.background)
                } else {
                    RoundedRectangle(cornerRadius: 24)
                        .stroke(.white, lineWidth: 3)
                        .frame(width: 240, height: 240)
                        .accessibilityHidden(true)
                }
            }
            .navigationTitle("pairing.scan_title")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.close") { dismiss() }
                }
            }
        }
    }
}
