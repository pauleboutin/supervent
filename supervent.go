package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"math"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"gopkg.in/yaml.v2"
)

const (
	DEFAULT_BATCH_SIZE = 100
)

type Config struct {
	Sources []SourceConfig `json:"sources"`
}

type SourceConfig struct {
	Name            string           `json:"name"`
	Vendor          string           `json:"vendor"`
	EventFormat     string           `json:"event_format"`
	TimestampFormat string           `json:"timestamp_format"`
	Fields          map[string]Field `json:"fields"`
}

type Field struct {
	Type        string      `json:"type"`
	Formats     []string    `json:"formats,omitempty"`
	Constraints Constraints `json:"constraints,omitempty"`
}

type Constraints struct {
	Min           string   `json:"min,omitempty"`
	Max           string   `json:"max,omitempty"`
	AllowedValues []string `json:"allowed_values,omitempty"`
}

type AxiomConfig struct {
	APIKey        string `yaml:"AXIOM_API_KEY"`
	Dataset       string `yaml:"AXIOM_DATASET"`
	HTTPBatchSize int    `yaml:"HTTP_BATCH_SIZE,omitempty"`
}

func loadConfig(filePath string) (Config, error) {
	var config Config
	file, err := os.ReadFile(filePath)
	if err != nil {
		return config, err
	}
	err = json.Unmarshal(file, &config)
	return config, err
}

func loadAxiomConfig(filePath string) (AxiomConfig, error) {
	var config AxiomConfig
	file, err := ioutil.ReadFile(filePath)
	if err != nil {
		return config, err
	}
	err = yaml.Unmarshal(file, &config)
	return config, err
}

func generateEvent(source SourceConfig) map[string]interface{} {
	event := map[string]interface{}{"source": source.Vendor}
	for field, details := range source.Fields {
		switch details.Type {
		case "datetime":
			switch source.TimestampFormat {
			case "UTC":
				event[field] = time.Now().UTC().Format(details.Formats[0])
			case "ISO":
				event[field] = time.Now().Format(time.RFC3339)
			case "Unix":
				event[field] = time.Now().Unix()
			case "RFC3339":
				event[field] = time.Now().Format(time.RFC3339)
			default:
				event[field] = time.Now().Format(source.TimestampFormat)
			}
		case "string":
			if len(details.Constraints.AllowedValues) > 0 {
				event[field] = details.Constraints.AllowedValues[rand.Intn(len(details.Constraints.AllowedValues))]
			} else {
				if field == "message" {
					if len(details.Formats) > 0 {
						selectedFormat := details.Formats[rand.Intn(len(details.Formats))]
						event[field] = strings.TrimSpace(selectedFormat)
					} else {
						event[field] = "No message format available"
					}
				} else {
					event[field] = generateRandomUsername()
				}
			}
		case "int":
			min := 0
			max := 100
			if details.Constraints.Min != "" {
				min, _ = strconv.Atoi(details.Constraints.Min)
			}
			if details.Constraints.Max != "" {
				max, _ = strconv.Atoi(details.Constraints.Max)
			}
			event[field] = rand.Intn(max-min) + min
		}
	}
	return event
}

// Removed unused function generateRandomIPAddress

func generateRandomUsername() string {
	usernames := []string{
		"john_doe", "jane_smith", "mohamed_ali", "li_wei", "maria_garcia",
		"yuki_tanaka", "olga_petrov", "raj_kumar", "fatima_zahra", "chen_wang",
		"ahmed_hassan", "isabella_rossi", "david_jones", "sophia_martinez", "emily_clark",
		"noah_brown", "mia_wilson", "lucas_miller", "oliver_davis", "ava_moore",
		"ethan_taylor", "amelia_anderson", "james_thomas", "harper_jackson", "benjamin_white",
		"liam_johnson", "emma_rodriguez", "william_lee", "sophia_kim", "mason_martin",
		"elijah_hernandez", "logan_lopez", "alexander_gonzalez", "sebastian_perez", "daniel_hall",
		"matthew_young", "henry_king", "jack_wright", "levi_scott", "isaac_green",
		"gabriel_baker", "julian_adams", "jayden_nelson", "lucas_carter", "anthony_mitchell",
		"grayson_perez", "dylan_roberts", "leo_turner", "jaxon_phillips", "asher_campbell",
		"ananya_sharma", "arjun_patel", "priya_singh", "vikram_gupta", "neha_verma",
		"sanjay_rana", "deepika_kapoor", "ravi_mehta", "sara_khan", "manoj_joshi",
		"željko_ivanović", "šime_šarić", "đorđe_đorđević", "čedomir_čolić", "žana_živković",
		"miloš_milošević", "ana_marija", "ivan_ivanov", "petar_petrov", "nikola_nikolić",
		"marta_novak", "katarina_kovač", "tomaž_tomažič", "matej_matejić", "vanja_vuković",
		"dragana_dimitrijević", "bojan_bojović", "milica_milovanović", "stefan_stefanović", "vanja_vasić",
		"igor_ilić", "jelena_jovanović", "marko_marković", "tanja_tomić", "zoran_zorić",
	}

	// Generate weights using Zipf's law
	weights := make([]float64, len(usernames))
	s := 1.07 // Zipf's law parameter
	for i := range weights {
		weights[i] = 1.0 / math.Pow(float64(i+1), s)
	}

	// Normalize weights
	totalWeight := 0.0
	for _, weight := range weights {
		totalWeight += weight
	}
	for i := range weights {
		weights[i] /= totalWeight
	}

	// Select a username based on the weights
	r := rand.Float64()
	for i, weight := range weights {
		r -= weight
		if r <= 0 {
			return usernames[i]
		}
	}
	return usernames[len(usernames)-1]
}

func sendBatch(events []map[string]interface{}, dataset, apiKey string) error {
	url := fmt.Sprintf("https://api.axiom.co/v1/datasets/%s/ingest", dataset)
	//fmt.Println("Sending batch of", len(events), "events to", url, "key", apiKey)
	body, err := json.Marshal(events)
	if err != nil {
		return err
	}
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", apiKey))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to send batch: %s", resp.Status)
	}
	return nil
}

func main() {
	// Define the --config flag
	configPath := flag.String("config", "config.json", "Path to the configuration file")
	flag.Parse()

	// Load the configuration file
	config, err := loadConfig(*configPath)
	if err != nil {
		fmt.Println("Error loading config:", err)
		return
	}

	// Load the Axiom configuration
	axiomConfig, err := loadAxiomConfig("axiom_config.yaml")
	if err != nil {
		fmt.Println("Error loading Axiom config:", err)
		return
	}

	batchSize := DEFAULT_BATCH_SIZE
	if axiomConfig.HTTPBatchSize > 0 {
		batchSize = axiomConfig.HTTPBatchSize
	}

	var allEvents []map[string]interface{}

	// Set up signal handling to gracefully exit on ^C
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		fmt.Println("Received interrupt signal, sending remaining events...")
		if len(allEvents) > 0 {
			err = sendBatch(allEvents, axiomConfig.Dataset, axiomConfig.APIKey)
			if err != nil {
				fmt.Println("Error sending batch:", err)
			} else {
				// fmt.Println("Batch sent successfully")
			}
		}
		os.Exit(0)
	}()

	// Generate events in a round-robin fashion indefinitely
	for {
		for _, source := range config.Sources {
			event := generateEvent(source)
			allEvents = append(allEvents, event)
			if len(allEvents) >= batchSize {
				err = sendBatch(allEvents, axiomConfig.Dataset, axiomConfig.APIKey)
				if err != nil {
					fmt.Println("Error sending batch:", err)
				} else {
					// fmt.Println("Batch sent successfully")
				}
				allEvents = allEvents[:0] // Clear the slice
			}
		}
	}
}
