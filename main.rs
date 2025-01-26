use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::mpsc;
use std::time::Instant;

#[derive(Debug, Serialize)]
struct Event {
    _time: DateTime<Utc>,
    source: String,
    message: String,
    attributes: EventAttributes,
}

#[derive(Debug, Serialize)]
struct EventAttributes {
    method: &'static str,
    path: &'static str,
    status: u16,
    bytes: u32,
}

static METHODS: [&str; 4] = ["GET", "POST", "PUT", "DELETE"];
static PATHS: [&str; 3] = ["/api/v1/users", "/api/v1/orders", "/api/v1/products"];

#[tokio::main]
async fn main() {
    let (tx, mut rx) = mpsc::channel(100);
    let start = Instant::now();
    let mut total_events = 0;

    // Spawn generator threads
    let mut handles = vec![];
    for i in 0..num_cpus::get() {
        let tx = tx.clone();
        let handle = tokio::spawn(async move {
            core_affinity::set_for_current(i);
            generate_events(tx).await;
        });
        handles.push(handle);
    }

    // Spawn uploader threads
    let mut upload_handles = vec![];
    for i in 0..15 {
        let mut rx = rx.clone();
        let handle = tokio::spawn(async move {
            while let Some(events) = rx.recv().await {
                upload_events(events, i).await;
                total_events += events.len();
                
                if total_events % 1_000_000 == 0 {
                    let elapsed = start.elapsed().as_secs_f64();
                    println!("Generated {} events in {:.2f} seconds ({:.2f} events/sec)",
                        total_events, elapsed, total_events as f64 / elapsed);
                }
            }
        });
        upload_handles.push(handle);
    }

    // Wait for completion
    for handle in handles {
        handle.await.unwrap();
    }
}
