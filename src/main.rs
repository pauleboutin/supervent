use chrono::{DateTime, Utc};
use serde::Serialize;
use std::env;
use tokio::sync::broadcast;
use std::time::Instant;
use std::time::Duration;
use lazy_static::lazy_static;

#[derive(Debug, Serialize, Clone)]
struct Event {
    _time: DateTime<Utc>,
    source: String,
    message: String,
    attributes: EventAttributes,
}

#[derive(Debug, Serialize, Clone)]
struct EventAttributes {
    method: &'static str,
    path: &'static str,
    status: u16,
    bytes: u32,
}

static METHODS: [&str; 4] = ["GET", "POST", "PUT", "DELETE"];
static PATHS: [&str; 3] = ["/api/v1/users", "/api/v1/orders", "/api/v1/products"];

lazy_static! {
    static ref CLIENT: reqwest::Client = {
        reqwest::Client::builder()
            .pool_max_idle_per_host(100)
            .tcp_nodelay(true)
            .timeout(Duration::from_secs(30))
            .build()
            .unwrap()
    };
}

#[tokio::main]
async fn main() {
    let (tx, _rx) = broadcast::channel::<Vec<Event>>(1000);
    let start = Instant::now();
    let mut total_events = 0;

    // Use all AWS NICs
    let n_interfaces = 15;

    // Use all AWS cores
    let mut handles = vec![];
    for _ in 0..64 {  // Use all AWS cores
        let tx = tx.clone();
        let handle = tokio::spawn(async move {
            generate_events(tx).await;
        });
        handles.push(handle);
    }

    // Spawn one uploader per NIC
    let mut upload_handles = vec![];
    for interface in 0..n_interfaces {
        let mut rx = tx.subscribe();
        let upload_handle = tokio::spawn(async move {
            while let Ok(events) = rx.recv().await {
                upload_events(&events, interface).await;
                total_events += events.len();
                drop(events);
                
                if total_events % 1_000_000 == 0 {
                    let elapsed = start.elapsed().as_secs_f64();
                    println!("Generated {} events in {:.2} seconds ({:.2} events/sec)",
                        total_events, elapsed, total_events as f64 / elapsed);
                }
            }
        });
        upload_handles.push(upload_handle);
    }

    // Wait for completion
    for handle in handles {
        handle.await.unwrap();
    }
    for upload_handle in upload_handles {
        upload_handle.await.unwrap();
    }
}

async fn generate_events(tx: broadcast::Sender<Vec<Event>>) {
    let mut events = Vec::with_capacity(1_000_000);
    let start_time = Utc::now();
    
    loop {
        // Zero-allocation event generation
        let event = Event {
            _time: start_time + chrono::Duration::seconds(fastrand::i64(0..3600)),
            source: String::from("web_server"),
            message: String::from("access log"),
            attributes: EventAttributes {
                method: METHODS[fastrand::usize(..METHODS.len())],
                path: PATHS[fastrand::usize(..PATHS.len())],
                status: 200,
                bytes: fastrand::u32(500..5000),
            },
        };
        
        events.push(event);
        
        if events.len() >= 1_000_000 {
            if tx.send(events).is_err() {
                break;
            }
            events = Vec::with_capacity(1_000_000);
        }
    }
}

async fn upload_events(events: &Vec<Event>, interface_id: usize) {
    let token = env::var("AXIOM_TOKEN").expect("AXIOM_TOKEN must be set");
    let url = format!("https://api.axiom.co/v1/datasets/supervent/ingest");
    
    let result = CLIENT.post(&url)
        .header("Authorization", format!("Bearer {}", token))
        .json(&events)
        .send()
        .await;
        
    match result {
        Ok(_) => println!("Interface {}: Sent {} events", interface_id, events.len()),
        Err(e) => eprintln!("Interface {}: Error sending events: {}", interface_id, e),
    }
}
