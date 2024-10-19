package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/mroth/weightedrand"
)

// Default batch size
const DEFAULT_BATCH_SIZE = 200

// Configuration
type Config struct {
	AxiomDataset string
	AxiomAPIKey  string
	BatchSize    int
}

// Sample Data
var hostnames, ipAddresses, macAddresses, oracleUsernames, oracleActions []string

// Precomputed Choices
var precomputedHostnames, precomputedIPAddresses, precomputedMacAddresses, precomputedOracleUsernames, precomputedOracleActions, precomputedGPActions []string

// User Agents and Weights
var userAgents = []string{
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
	"Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/16.16299",
	"Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Mobile Safari/537.36",
	"Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
	"Mozilla/5.0 (Linux; Android 10; SAMSUNG SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/12.0 Chrome/79.0.3945.136 Mobile Safari/537.36",
}
var userAgentWeights = []uint{30, 15, 10, 15, 5, 20, 15, 5}

// Weighted Random Generators
var userAgentChooser *weightedrand.Chooser

// Burst Mode and Burst Count
var burstMode int
var burstCount int

// Define Great Plains actions
var gp_actions = []string{"login", "search", "view_product", "add_to_cart", "purchase", "logout"}

// Define Customer Journey Actions and Weights
var customerJourneyActions = []string{"search", "view_product", "add_to_cart", "purchase"}
var customerJourneyWeights = []uint{40, 30, 20, 10}

// Define Service Names and Weights
var serviceNames = []string{
	"auth-service", "search-service", "payment-service", "user-service",
	"inventory-service", "order-service", "oracle-service", "gp-service",
}
var serviceNameWeights = []uint{5, 5, 5, 50, 5, 5, 2, 2}

// Define Search Terms and Weights
var searchTerms = []string{"shoes", "laptop", "phone", "book", "clothes", "Apple", "Tesla", "iPhone", "Galaxy"}
var searchTermWeights = []uint{100, 50, 33, 25, 20, 17, 14, 12, 10}

// Initialize weighted random choosers
func init() {
	rand.Seed(time.Now().UnixNano())

	// Initialize weighted random chooser for user agents
	choices := make([]weightedrand.Choice, len(userAgents))
	for i, ua := range userAgents {
		choices[i] = weightedrand.Choice{Item: ua, Weight: userAgentWeights[i]}
	}
	var err error
	userAgentChooser, err = weightedrand.NewChooser(choices...)
	if err != nil {
		log.Fatalf("Failed to create weighted random chooser: %v", err)
	}
}

// Read configuration from file
func readConfig(filePath string) Config {
	file, err := os.Open(filePath)
	if err != nil {
		log.Fatalf("Failed to open config file: %v", err)
	}
	defer file.Close()

	config := Config{
		BatchSize: DEFAULT_BATCH_SIZE, // Use default BatchSize
	}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key, value := parts[0], parts[1]
		switch key {
		case "AXIOM_DATASET":
			config.AxiomDataset = value
		case "AXIOM_API_KEY":
			config.AxiomAPIKey = value
		case "BATCH_SIZE":
			config.BatchSize, _ = strconv.Atoi(value)
		}
	}
	if err := scanner.Err(); err != nil {
		log.Fatalf("Failed to read config file: %v", err)
	}
	return config
}

// Read sample data from file
func readSampleData(filePath string) []string {
	file, err := os.Open(filePath)
	if err != nil {
		log.Fatalf("Failed to open sample data file: %v", err)
	}
	defer file.Close()

	var data []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		data = append(data, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		log.Fatalf("Failed to read sample data file: %v", err)
	}
	return data
}

// Generate a random log record
func generateLogRecord() map[string]interface{} {
	timestamp := time.Now().Unix()
	record := map[string]interface{}{
		"timestamp":   time.Unix(timestamp, 0).Format(time.RFC3339),
		"_time":       timestamp,
		"user_id":     generateZipfianUserID(20000),
		"level":       randomChoice([]string{"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}, []uint{10, 50, 20, 15, 5}),
		"logger":      "custom_logger",
		"protocol":    randomChoice([]string{"HTTP", "HTTPS", "FTP", "SSH"}, []uint{50, 40, 5, 5}),
		"source_port": rand.Intn(65535-1024) + 1024,
		"dest_port":   randomChoice([]int{80, 443, 21, 22}, []uint{50, 40, 5, 5}),
		"packet_size": rand.Intn(1500-64) + 64,
		"duration":    round(rand.Float64()*9.9+0.1, 2),
		"bytes_xferd": rand.Intn(1000000-100) + 100,
		"source_ip":   randomChoice(precomputedIPAddresses, nil),
		"dest_ip":     randomChoice(precomputedIPAddresses, nil),
		"user_agent":  userAgentChooser.Pick().(string),
		"http_stat":   generateHTTPStatusCode(),
	}
	if rand.Intn(10) == 0 {
		record["trace_id"] = uuid.New().String()
		record["span_id"] = uuid.New().String()
	}
	if rand.Intn(2) == 0 {
		record["service_name"] = randomChoice(serviceNames, serviceNameWeights)
	}
	if record["service_name"] == "user-service" {
		record["timestamp"] = time.Unix(timestamp, 0).Format("2006-01-02 15:04:05")
	}
	if rand.Intn(2) == 0 {
		record["custom_host_name"] = randomChoice(precomputedHostnames, nil)
	}
	if rand.Intn(2) == 0 {
		record["http_method"] = randomChoice([]string{"GET", "POST", "PUT", "DELETE"}, nil)
		record["http_url"] = randomChoice([]string{"/api/v1/resource", "/api/v1/resource/1", "/api/v1/resource/2", "/api/v1/login", "/api/v1/logout", "/api/v1/search", "/api/v1/purchase"}, nil)
	}
	if record["service_name"] == "oracle-service" {
		record["oracle_username"] = randomChoice(precomputedOracleUsernames, nil)
		record["oracle_action"] = randomChoice(precomputedOracleActions, nil)
	}
	if record["service_name"] == "gp-service" {
		record["gp_action"] = randomChoice(precomputedGPActions, nil)
	}
	// Add customer journey actions
	if record["service_name"] == "user-service" {
		action := randomChoice(customerJourneyActions, customerJourneyWeights).(string)
		record["action"] = action
		if action == "search" {
			record["search_term"] = randomChoice(searchTerms, searchTermWeights).(string)
		} else if action == "view_product" {
			record["product_id"] = rand.Intn(10000)
		} else if action == "add_to_cart" {
			record["product_id"] = rand.Intn(10000)
			record["quantity"] = rand.Intn(5) + 1
		} else if action == "purchase" {
			record["order_id"] = uuid.New().String()
			record["total_amount"] = round(rand.Float64()*100+10, 2)
		}
	}
	fmt.Println(record["timestamp"])
	return record
}

// Generate a Zipfian user ID
func generateZipfianUserID(maxID int) int64 {
	rank := rand.Float64()*(1.0-1e-10) + 1e-10 // Ensure rank is never zero
	return int64(float64(maxID) / math.Pow(rank, 1.5))
}

// Generate HTTP status codes with clustering
func generateHTTPStatusCode() int {
	if burstMode == 0 || burstCount <= 0 {
		burstMode = randomChoice([]int{200, 301, 404, 500}, []uint{300, 5, 4, 1}).(int)
		burstCount = rand.Intn(10) + 1
	}
	burstCount--
	return burstMode
}

// Round a float to a specified number of decimal places
func round(val float64, places int) float64 {
	shift := math.Pow(10, float64(places))
	return math.Floor(val*shift+0.5) / shift
}

// Random choice with optional weights
func randomChoice(choices interface{}, weights []uint) interface{} {
	switch v := choices.(type) {
	case []string:
		if weights == nil {
			return v[rand.Intn(len(v))]
		}
		choices := make([]weightedrand.Choice, len(v))
		for i, choice := range v {
			choices[i] = weightedrand.Choice{Item: choice, Weight: weights[i]}
		}
		chooser, err := weightedrand.NewChooser(choices...)
		if err != nil {
			log.Fatalf("Failed to create weighted random chooser: %v", err)
		}
		return chooser.Pick().(string)
	case []int:
		if weights == nil {
			return v[rand.Intn(len(v))]
		}
		choices := make([]weightedrand.Choice, len(v))
		for i, choice := range v {
			choices[i] = weightedrand.Choice{Item: choice, Weight: weights[i]}
		}
		chooser, err := weightedrand.NewChooser(choices...)
		if err != nil {
			log.Fatalf("Failed to create weighted random chooser: %v", err)
		}
		return chooser.Pick().(int)
	default:
		return nil
	}
}

// Send batch of log records to Axiom
func sendBatch(records []map[string]interface{}, config Config) {
	url := fmt.Sprintf("https://api.axiom.co/v1/datasets/%s/ingest", config.AxiomDataset)
	jsonData, err := json.Marshal(records)
	if err != nil {
		log.Fatalf("Failed to marshal records: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		log.Fatalf("Failed to create request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", config.AxiomAPIKey))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		log.Fatalf("Failed to send request: %v", err)
	}
	defer resp.Body.Close()

	body, _ := ioutil.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		log.Fatalf("Failed to send batch: %s", body)
	}
}

func main() {
	config := readConfig("axiom_config.txt")

	// Read sample data
	hostnames = readSampleData("../eventgen/samples/hostname.sample")
	ipAddresses = readSampleData("../eventgen/samples/ip_address.sample")
	macAddresses = readSampleData("../eventgen/samples/mac_address.sample")
	oracleUsernames = readSampleData("../eventgen/samples/oracleUserNames.sample")
	oracleActions = readSampleData("../eventgen/samples/oracle11.action.sample")

	// Print the value of BatchSize
	fmt.Println("BatchSize:", config.BatchSize)

	// Precompute random choices
	precomputedHostnames = make([]string, 1000)
	precomputedIPAddresses = make([]string, 1000)
	precomputedMacAddresses = make([]string, 1000)
	precomputedOracleUsernames = make([]string, 1000)
	precomputedOracleActions = make([]string, 1000)
	precomputedGPActions = make([]string, 1000)
	for i := 0; i < 1000; i++ {
		precomputedHostnames[i] = hostnames[rand.Intn(len(hostnames))]
		precomputedIPAddresses[i] = ipAddresses[rand.Intn(len(ipAddresses))]
		precomputedMacAddresses[i] = macAddresses[rand.Intn(len(macAddresses))]
		precomputedOracleUsernames[i] = oracleUsernames[rand.Intn(len(oracleUsernames))]
		precomputedOracleActions[i] = oracleActions[rand.Intn(len(oracleActions))]
		precomputedGPActions[i] = gp_actions[rand.Intn(len(gp_actions))]
	}

	// Set up signal handling
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Generate and send log records
	records := make([]map[string]interface{}, 0, config.BatchSize)
	done := make(chan bool)

	go func() {
		for {
			record := generateLogRecord()
			records = append(records, record)
			if len(records) >= config.BatchSize {
				sendBatch(records, config)
				records = records[:0]
			}
			time.Sleep(1 * time.Millisecond) // Simulate some delay between events
		}
	}()

	// Wait for termination signal
	go func() {
		<-sigChan
		fmt.Println("Termination signal received. Sending remaining batch...")
		if len(records) > 0 {
			sendBatch(records, config)
		}
		done <- true
	}()

	<-done
}
