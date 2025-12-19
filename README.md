# Confluence Cloud Storage Analyzer

**Version:** V1.1 \
**Author:** Frieder Scharpf \
**Description:** A Python tool for analyzing storage used by attachments in Confluence Cloud Free, Standard and Premium.

**DISCLAIMER:** This script was mainly created from ChatGPT. Please use with care! In case of any doubts about security reasons please check source code first or do not use this script.

## Overview

The **Confluence Cloud Storage Analyzer** is a Python based utility that uses the Confluence REST API to perform a complete audit of storage used by attachments within a Confluence Cloud instance. It analyzes spaces, pages, and attachments to help users understand where storage is consumed and which files can safely be removed.

It provides:

* Per space storage statistics
* Lists of the **largest attachments** per space
* Detection of whether a file is **embedded on its parent page**
* Detection of whether a file is **linked from other pages**
* Lists of **unreferenced attachments** per space
* All attachment versions are considered by the analysis
* CSV exports of attachments and unreferenced attachments lists
* Interactive **HTML reports** of the CSV exports with sortable tables
* A global **index page** linking all reports
* UI delete links working with all plans also for Free plan users
* Direct REST API delete links for Standard and Premium plans

All output is stored in a timestamped folder.

## Use Cases

* Cleaning up old Confluence spaces
* Identifying large unused attachments
* Find duplicates of attachments that were created by not carefully duplicating a site
* Reducing storage usage on the Confluence Free plan
* Migration planning
* Auditing attachment usage

## Requirements

* Python 3.10 or newer
* requests library
* No additional third party packages

## Configuration

There are two options to configure the credentials for Confluence. The first one is to add the credentials directly to the script and the second one is to use a configuration file.
 
To add the credentials to the script, edit the following variables: BASE_URL, API_USER, API_TOKEN
Example:
BASE_URL = "[https://YOUR_DOMAIN.atlassian.net/wiki](https://YOUR_DOMAIN.atlassian.net/wiki)"
API_USER = "YOUR_EMAIL"
API_TOKEN = "YOUR_API_TOKEN"

To use the configuration file, create a file with the name + file extention: **confluence_storage_analyzer.cfg** and the following content:
[confluence]
base_url = https://your-domain.atlassian.net/wiki
api_user = your.email@example.com
api_token = your_api_token_here

If the configuration file exists, its values are used only if the corresponding variables in the script are empty.
You can also remove the suffix from the template file in the repo and add your Confluence credentials there.

## Running the Analysis

Run the script with:
python confluence_storage_analyzer_Vmajor_minor.py

After completion open index.html, located in the directory created by the analysis run, in your browser.

## Confluence Free Plan Limitation

Deleting attachments via the REST API is not available on the Free plan.
The reports therefore include UI delete links that work on all plans.

## Key Features

### Full storage analytics

The script collects and analyzes:

* Spaces
* Pages
* Attachments including all versions
* Storage format content of each page
* Embedded media
* Hyperlinks to attachments
* Cross page references

### Accurate embedding and linking detection

For each attachment the tool checks:

1. Embedded on the parent page
2. Linked from other pages
3. Unreferenced anywhere

All attachment **versions** are checked, not just the latest version.

## Output Structure

The script generates a folder named similar to:
confluence_analysis_Vmajor_minor_YYYY-MM-dd_HH-mm-ss

Inside the folder:

* index.html
* directory for each space named like SPACEKEY/
    * SPACEKEY_attachments.csv
    * SPACEKEY_attachments.html
    * SPACEKEY_unreferenced.csv
    * SPACEKEY_unreferenced.html

## Output Files Explained

### index.html

The main dashboard containing:

* A list of all spaces
* Storage usage per space
* Links to the attachment report per space
* Links to the unreferenced attachment report per space
* A counter showing the number of unreferenced attachments per space

### Attachment Reports - SPACEKEY_attachments.html

This report lists the top 100 biggest attachments in the space including:

| Column | Description | 
|--------|-------------|
| File Name | Attachment filename |
| File size | File size in KB/MB |
| Owning page (link) | Page where file is attached |
| Embedded on owning page? | Yes/No — whether used in content |
| Linked Elsewhere? | List of pages referencing this file |
| Delete via Confluence UI link | Link to Confluence’s built-in attachment delete screen |
| Delete via REST API link | Direct REST delete endpoint (Standard/Premium only) |

All columns are sortable in the browser by clicking the column head.

### Unreferenced Attachment Reports - SPACEKEY_unreferenced.html

Lists all attachments of the space where none of their versions are:

* Embedded on their owning page or
* Linked from any other page or

Attachments in this report are typically safe to delete.

## CSV Exports

For each space the following CSV files are generated in the SPACEKEY directory:

* SPACEKEY_attachments.csv
* SPACEKEY_unreferenced.csv

Example format:
Filename, Size(Bytes), Size(MB), Download URL, Original Page, Linked on Page, Linked on Other Pages, Attachment Page Link, API Delete Link

The CSV files can be imported into spreadsheet tools or other analysis systems.

## How Attachment Usage Is Detected

For each attachment all versions are analyzed.

An attachment is considered used if at least one version is:

* Embedded on the owning page
* Linked from another page

Only if no version is referenced anywhere the attachment is marked as unreferenced.

Special characters in file names are handled using URL encoding and HTML escaping.

### REST API usage

The script uses only endpoints available in the Free plan, including:
GET /wiki/rest/api/space
GET /wiki/rest/api/content?spaceKey=...
GET /wiki/rest/api/content/{id}/child/attachment?expand=version
GET /wiki/rest/api/content/{id}?expand=body.storage
GET /wiki/rest/api/content/{attachment_id}?expand=version

### Processing steps

1. Fetch spaces
2. Fetch pages per space
3. Fetch attachments
4. Load page storage content
5. Detect embedded media
6. Detect links to attachments
7. Analyze all attachment versions:
   An attachment is considered used if at least one of its versions is
   embedded on its owning page or linked from any other page.
8. Produce HTML + CSV reports

## License

This project is licensed under the Apache License 2.0.
See the LICENSE file for details.

## Summary

The Confluence Cloud Storage Analyzer provides a complete interactive overview of attachment storage usage in Confluence Cloud.

It is designed to be safe, transparent, and easy to use while providing enough detail to make informed cleanup decisions.

