name: Add URLs in Sitemaps

on:
  workflow_dispatch:

jobs:
  run_script:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v2

      - name: Set up Go
        uses: actions/setup-go@v2
        with:
          go-version: '1.17'

      - name: Run Sitemap Script
        run: |
          go run sitemap.go
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add .
          git commit -m "Update XML files"
          git push origin main
