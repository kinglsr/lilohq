import streamlit as st
from elasticsearch import Elasticsearch

import json
from pathlib import Path
from elasticsearch import Elasticsearch, helpers
from fuzzywuzzy import process
from dotenv import load_dotenv
import os

base_dir = "/Users/sairamlingineni/Documents/lilohq/"

load_dotenv(os.path.join(base_dir, ".env"))

ES_HOST = os.getenv("ES_HOST")
ES_API_KEY = os.getenv("ES_API_KEY")

es = Elasticsearch(
    hosts=[ES_HOST],
    api_key=ES_API_KEY,
)

# Check connection
if es.ping():
    print("Connected to Elasticsearch")
else:
    print("Connection failed")

INDEX_NAME = "products"
# UI Title
st.title("LILOHQ Product Search")


# -----------------------------
# First: Get category hierarchy from ES aggs
# -----------------------------
agg_query = {
    "size": 0,  # no hits, just aggs
    "aggs": {
        "l1": {
            "terms": {"field": "category.l1", "size": 100},
            "aggs": {
                "l2": {
                    "terms": {"field": "category.l2", "size": 200},
                    "aggs": {
                        "l3": {"terms": {"field": "category.l3", "size": 300}}
                    }
                }
            }
        }
    }
}

agg_res = es.search(index=INDEX_NAME, body=agg_query)

# Build hierarchy dictionary for dropdowns
category_hierarchy = {}
for l1_bucket in agg_res["aggregations"]["l1"]["buckets"]:
    l1_name = l1_bucket["key"]
    category_hierarchy[l1_name] = {}
    for l2_bucket in l1_bucket["l2"]["buckets"]:
        l2_name = l2_bucket["key"]
        category_hierarchy[l1_name][l2_name] = [
            l3_bucket["key"] for l3_bucket in l2_bucket["l3"]["buckets"]
        ]

# -----------------------------
# Sidebar Filters (dynamic)
# -----------------------------
st.sidebar.header("Filters")

query = st.text_input("Search products:")

# Dynamic dropdowns
l1_options = ["(Any)"] + list(category_hierarchy.keys())
selected_l1 = st.sidebar.selectbox("Category Level 1", l1_options)

# l2 depends on l1
if selected_l1 != "(Any)":
    l2_options = ["(Any)"] + list(category_hierarchy[selected_l1].keys())
else:
    l2_options = ["(Any)"]
selected_l2 = st.sidebar.selectbox("Category Level 2", l2_options)

# l3 depends on l2
if selected_l1 != "(Any)" and selected_l2 != "(Any)":
    l3_options = ["(Any)"] + category_hierarchy[selected_l1][selected_l2]
else:
    l3_options = ["(Any)"]
selected_l3 = st.sidebar.selectbox("Category Level 3", l3_options)

inventory_filter = st.sidebar.multiselect(
    "Inventory Status", ["in_stock", "out_of_stock"]
)


# -----------------------------
# Build ES Filters
# -----------------------------
filters = []

if selected_l1 != "(Any)":
    filters.append({"term": {"category.l1": selected_l1}})
if selected_l2 != "(Any)":
    filters.append({"term": {"category.l2": selected_l2}})
if selected_l3 != "(Any)":
    filters.append({"term": {"category.l3": selected_l3}})
if inventory_filter:
    filters.append({"terms": {"inventory_status": inventory_filter}})


# -----------------------------
# Build ES Query with Hierarchical Aggs
# -----------------------------
es_query_hybrid = {
  "size": 100,
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": query if query else "",
            "fields": ["title^3", "description","category.raw"],
            "type": "best_fields",
            "operator": "or",
            "fuzziness": "AUTO",      
            "prefix_length": 1
          }
        }
      ],
      "filter": filters,
      "should": [
        {
          "semantic": {
            "field": "semantic_search",
            "query": query if query else "",
            "boost": 3
          }
        }
      ]
    }
  },
  "aggs": {
    "l1": {
      "terms": {
        "field": "category.l1",
        "size": 100
      },
      "aggs": {
        "l2": {
          "terms": {
            "field": "category.l2",
            "size": 200
          },
          "aggs": {
            "l3": {
              "terms": {
                "field": "category.l3",
                "size": 300
              }
            }
          }
        }
      }
    },
    "inventory_status": {
      "terms": {
        "field": "inventory_status",
        "size": 10
      }
    }
  },
  "sort": [
    {
      "inventory_status": {
        "order": "asc"
      }
    }
  ]
}

es_query_rank = {
    "retriever": {
        "linear": {
            "rank_window_size": 100,
            "retrievers": [
                {
                    "retriever": {
                        "standard": {
                            "query": {
                                "match": {
                                    "semantic_search": query if query else ""
                                }
                            }
                        }
                    },
                    "normalizer": "none"
                },
                {
                    "retriever": {
                        "standard": {
                            "query": {
                                "bool": {
                                    "must": [
                                        {
                                            "multi_match": {
                                                "query": query if query else "",
                                                "fields": ["title^3", "description", "category.raw^2"],
                                                "type": "best_fields",
                                                "operator": "or",
                                                "fuzziness": "AUTO",
                                                "prefix_length": 1
                                            }
                                        }
                                    ],
                                    "filter": filters
                                }
                            }
                        }
                    },
                    "weight": 50 
                }
            ]
        }
    },
    "aggs": {
        "l1": {
            "terms": {
                "field": "category.l1",
                "size": 100
            },
            "aggs": {
                "l2": {
                    "terms": {
                        "field": "category.l2",
                        "size": 200
                    },
                    "aggs": {
                        "l3": {
                            "terms": {
                                "field": "category.l3",
                                "size": 300
                            }
                        }
                    }
                }
            }
        },
        "inventory_status": {
            "terms": {
                "field": "inventory_status",
                "size": 10
            }
        }
    }
}



res = es.search(index=INDEX_NAME, body=es_query_hybrid)
st.write(f"### Total results: {res['hits']['total']['value']}")


# Inventory facet
st.sidebar.subheader("Inventory Status")
for bucket in res["aggregations"]["inventory_status"]["buckets"]:
    st.sidebar.write(f"{bucket['key']} ({bucket['doc_count']})")
# -----------------------------
# Display Hierarchical Category Facet
# -----------------------------
st.sidebar.subheader("Category Facets")

for l1_bucket in res["aggregations"]["l1"]["buckets"]:
    st.sidebar.write(f"**{l1_bucket['key']} – {l1_bucket['doc_count']}**")

    for l2_bucket in l1_bucket["l2"]["buckets"]:
        st.sidebar.write(f"&nbsp;&nbsp;&nbsp;• {l2_bucket['key']} – {l2_bucket['doc_count']}")

        for l3_bucket in l2_bucket["l3"]["buckets"]:
            st.sidebar.write(
                f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- {l3_bucket['key']} – {l3_bucket['doc_count']}"
            )

# -----------------------------
# Display Product Results
# -----------------------------
for hit in res['hits']['hits']:
    src = hit["_source"]

    st.subheader(src.get("title", ""))

    # Category
    if "category" in src and "raw" in src["category"]:
        st.write("**Category:** " + src["category"]["raw"])

    # Inventory
    st.write(f"**Inventory:** {src.get('inventory_status')}")

    # Supplier rating
    st.write(f"**Supplier Rating:** {src.get('supplier_rating', '—')}")

     # description
    st.write(f"**description:** {src.get('description', '—')}")

    # Attributes
    attributes = src.get("attributes", [])
    if attributes:
        st.write("**Attributes:**")
        for a in attributes:
            st.write(f"- {a['name']}: {a['value']}")

    st.write("---")
