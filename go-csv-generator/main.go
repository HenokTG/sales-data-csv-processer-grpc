package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"time"
)

type Config struct {
	NumRecords     int    `json:"num_records"`
	NumDepartments int    `json:"num_departments"`
	OutputFile     string `json:"output_file"`
}

func loadConfig() Config {
	file, err := os.ReadFile("config.json")
	if err != nil {
		fmt.Println("⚠️  config.json not found, using defaults.")
		return Config{NumRecords: 1_000_000, NumDepartments: 100, OutputFile: "output.csv"}
	}

	var config Config
	json.Unmarshal(file, &config)

	if config.NumRecords == 0 {
		config.NumRecords = 1_000_000
	}
	if config.NumDepartments == 0 {
		config.NumDepartments = 100
	}
	if config.OutputFile == "" {
		config.OutputFile = "output.csv"
	}

	return config
}

func main() {
	config := loadConfig()

	fmt.Printf("\nGenerating CSV...\nRecords: %d\nDepartments: %d\nOutput: %s\n\n",
		config.NumRecords, config.NumDepartments, config.OutputFile)

	departments := make([]string, config.NumDepartments)
	for i := 0; i < config.NumDepartments; i++ {
		departments[i] = fmt.Sprintf("Department %d", i+1)
	}

	file, _ := os.Create(config.OutputFile)
	defer file.Close()
	writer := bufio.NewWriter(file)

	fmt.Fprintln(writer, "Department Name,Date,Number of Sales")

	rand.Seed(time.Now().UnixNano())
	baseDate := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	for i := 0; i < config.NumRecords; i++ {
		dept := departments[rand.Intn(config.NumDepartments)]
		date := baseDate.AddDate(0, 0, rand.Intn(365))
		sales := rand.Intn(491) + 10

		fmt.Fprintf(writer, "%s,%s,%d\n", dept, date.Format("2006-01-02"), sales)

		if i%1_000_000 == 0 {
			writer.Flush()
			fmt.Printf("Written %d rows...\n", i)
		}
	}

	writer.Flush()
	fmt.Println("✅ CSV generation completed.")
}
