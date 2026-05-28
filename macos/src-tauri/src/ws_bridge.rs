use futures_util::{SinkExt, StreamExt};
use native_tls::TlsConnector;
use std::sync::Arc;
use tauri::{AppHandle, Emitter, Runtime, State};
use tokio::sync::{mpsc, Mutex};
use tokio_tungstenite::{tungstenite::client::IntoClientRequest, Connector};
use tungstenite::protocol::{Message, WebSocketConfig};

type WsStream = tokio_tungstenite::WebSocketStream<
    tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
>;

pub(crate) struct WsBridge {
    sender: Option<mpsc::Sender<Message>>,
}

impl WsBridge {
    fn new() -> Self {
        Self { sender: None }
    }
}

#[tauri::command]
pub async fn ws_connect<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Arc<Mutex<WsBridge>>>,
    url: String,
) -> Result<(), String> {
    let connector = TlsConnector::builder()
        .danger_accept_invalid_certs(true)
        .danger_accept_invalid_hostnames(true)
        .build()
        .map_err(|e| format!("TLS connector error: {e}"))?;

    let request = url
        .as_str()
        .into_client_request()
        .map_err(|e| format!("Invalid URL: {e}"))?;

    let mut config = WebSocketConfig::default();
    config.max_message_size = Some(16 * 1024 * 1024);
    config.max_frame_size = Some(16 * 1024 * 1024);

    let ws_stream: WsStream = tokio_tungstenite::connect_async_tls_with_config(
        request,
        Some(config),
        false,
        Some(Connector::NativeTls(connector.into())),
    )
    .await
    .map_err(|e| format!("WebSocket connect failed: {e}"))?
    .0;

    let (mut ws_write, mut ws_read) = ws_stream.split();
    let (tx, mut rx) = mpsc::channel::<Message>(256);

    {
        let mut bridge = state.lock().await;
        bridge.sender = Some(tx);
    }

    tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if ws_write.send(msg).await.is_err() {
                break;
            }
        }
    });

    let app_read = app.clone();
    tokio::spawn(async move {
        while let Some(result) = ws_read.next().await {
            match result {
                Ok(Message::Text(text)) => {
                    let s = text.as_str().to_string();
                    let _ = app_read.emit("ws-message", s);
                }
                Ok(Message::Binary(data)) => {
                    let _ = app_read.emit("ws-binary", data.to_vec());
                }
                Ok(Message::Close(frame)) => {
                    let code: u16 = frame.as_ref().map(|f| f.code.into()).unwrap_or(0);
                    let reason = frame
                        .as_ref()
                        .map(|f| f.reason.to_string())
                        .unwrap_or_default();
                    let _ = app_read.emit(
                        "ws-close",
                        serde_json::json!({ "code": code, "reason": reason }),
                    );
                    break;
                }
                Ok(_) => {}
                Err(e) => {
                    let _ = app_read.emit("ws-error", e.to_string());
                    break;
                }
            }
        }
    });

    let _ = app.emit("ws-open", ());
    Ok(())
}

#[tauri::command]
pub async fn ws_send_text(
    state: State<'_, Arc<Mutex<WsBridge>>>,
    message: String,
) -> Result<(), String> {
    let bridge = state.lock().await;
    match &bridge.sender {
        Some(sender) => sender
            .send(Message::text(message))
            .await
            .map_err(|e| format!("Send failed: {e}")),
        None => Err("Not connected".into()),
    }
}

#[tauri::command]
pub async fn ws_send_binary(
    state: State<'_, Arc<Mutex<WsBridge>>>,
    data: Vec<u8>,
) -> Result<(), String> {
    let bridge = state.lock().await;
    match &bridge.sender {
        Some(sender) => sender
            .send(Message::binary(data))
            .await
            .map_err(|e| format!("Send failed: {e}")),
        None => Err("Not connected".into()),
    }
}

#[tauri::command]
pub async fn ws_disconnect(
    state: State<'_, Arc<Mutex<WsBridge>>>,
) -> Result<(), String> {
    let mut bridge = state.lock().await;
    if let Some(sender) = bridge.sender.take() {
        let _ = sender.send(Message::Close(None)).await;
    }
    Ok(())
}

pub fn ws_bridge_state() -> Arc<Mutex<WsBridge>> {
    Arc::new(Mutex::new(WsBridge::new()))
}
