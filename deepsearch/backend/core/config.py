class Config:
    ARXIV_BASE_URL = "http://export.arxiv.org/api/query"
    BIORXIV_API_BASE_URL = "https://api.biorxiv.org"
    PMC_ESEARCH_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    PMC_EFETCH_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    PMC_DB = "pmc"
    PMC_API_EMAIL = "research@example.com" # PMC API email for Entrez tools
    DOAJ_API_BASE_URL = "https://doaj.org/api/v2"
    PLOS_API_BASE_URL = "http://api.plos.org/search"
    CORE_API_BASE_URL = "https://api.core.ac.uk/v3"
    CORE_API_KEY = "YOUR_CORE_API_KEY" # Replace with your actual CORE API key
    ARXIV_RSS_BASE_URL = "https://export.arxiv.org/rss"
    DEFAULT_CRAWLER_MAX_RESULTS = 10
    ARXIV_DELAY = 3.0 # seconds
    ARXIV_MAX_RESULTS = 50 # max per request
    ARXIV_DEFAULT_LIMIT = 20 # default limit for arXiv crawler

    SUPPORTED_CRAWLER_PLATFORMS = ["arxiv", "biorxiv", "pmc", "plos", "doaj", "arxiv_rss"] # supported platforms 