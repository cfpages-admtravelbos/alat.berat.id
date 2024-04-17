package main

import (
    "bytes"
    "fmt"
    "io/ioutil"
    "os"
    "path/filepath"
    "strings"
)

func main() {
    // Get the current directory
    dir, err := os.Getwd()
    if err != nil {
        fmt.Println("Error getting current directory:", err)
        return
    }

    // Get the GitHub repository name from the current directory
    repoName := strings.ToLower(filepath.Base(dir))

    // Walk through the current directory
    err = filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }
        if info.IsDir() {
            return nil
        }
        // Check for files with .xml extension
        if filepath.Ext(path) == ".xml" {
            // Read file contents
            content, err := ioutil.ReadFile(path)
            if err != nil {
                return err
            }
            // Replace "loc>/" with "loc>https://[githubrepositorynameinlowercase]/"
            updatedContent := bytes.Replace(content, []byte("loc>/"), []byte(fmt.Sprintf("loc>https://%s/", repoName)), -1)
            // Write updated content back to the file
            err = ioutil.WriteFile(path, updatedContent, 0644)
            if err != nil {
                return err
            }
            fmt.Println("Updated", path)
        }
        return nil
    })
    if err != nil {
        fmt.Println("Error walking through directory:", err)
        return
    }

    fmt.Println("Replacement completed successfully.")
}
