import streamlit as st
from elasticsearch import Elasticsearch
import os
#from dotenv import load_dotenv


##base_dir = "/Users/sairamlingineni/Documents/lilohq/"

##load_dotenv(os.path.join(base_dir, ".env"))

ES_HOST = os.getenv("ES_HOST")
ES_API_KEY = os.getenv("ES_API_KEY")


if not ES_HOST or not ES_API_KEY:
    st.error("Missing ES_HOST or ES_API_KEY environment variables.")
    st.stop()

es = Elasticsearch(
    hosts=[ES_HOST],
    api_key=ES_API_KEY,
)

st.title("LILOHQ Product Search")

INDEX_NAME = "products"


# -----------------------------
# Build Attribute Filter
# -----------------------------
def build_attribute_filter(attr_obj):
    nested_clauses = []
    for name, value in attr_obj.items():
        nested_clauses.append(
            {
                "nested": {
                    "path": "attributes",
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"attributes.name": name}},
                                {"term": {"attributes.value": value}},
                            ]
                        }
                    },
                }
            }
        )
    return nested_clauses


# -----------------------------
# Hybrid Search Function
# -----------------------------
def search_hybrid(query_text, filters):
    query = {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": query_text if query_text else "",
                        "fields": ["title^3", "description", "category.raw"],
                        "type": "best_fields",
                        "operator": "or",
                        "fuzziness": "AUTO",
                        "prefix_length": 1,
                    }
                }
            ],
            "filter": filters,
            "should": [
                {
                    "semantic": {
                        "field": "semantic_search",
                        "query": query_text if query_text else "",
                        "boost": 3,
                    }
                }
            ],
        }
    }
    body = {
        "size": 30,
        "query": query,
        "aggs": {
            "attributes": {
                "nested": {"path": "attributes"},
                "aggs": {
                    "by_name": {
                        "terms": {"field": "attributes.name", "size": 3},
                        "aggs": {
                            "by_value": {
                                "terms": {"field": "attributes.value", "size": 3}
                            }
                        },
                    }
                },
            },
            "l1": {
                "terms": {"field": "category.l1", "size": 10},
                "aggs": {
                    "l2": {
                        "terms": {"field": "category.l2", "size": 20},
                        "aggs": {"l3": {"terms": {"field": "category.l3", "size": 30}}},
                    }
                },
            },
            "inventory_status": {"terms": {"field": "inventory_status", "size": 10}},
        },
    }

    # print('ES Query:',body)
    results = es.search(index=INDEX_NAME, body=body)
    return (results, query)


#-----------------------------
# Filter-Only Search Function
#-----------------------------
def search_filters(filters):
    query = {
        "bool": {
            "filter": filters
        }
    }
    body = {
        "size": 30,
        "query": query,
        "aggs": {
            "attributes": {
                "nested": {"path": "attributes"},
                "aggs": {
                    "by_name": {
                        "terms": {"field": "attributes.name", "size": 3},
                        "aggs": {
                            "by_value": {
                                "terms": {"field": "attributes.value", "size": 3}
                            }
                        },
                    }
                },
            },
            "l1": {
                "terms": {"field": "category.l1", "size": 10},
                "aggs": {
                    "l2": {
                        "terms": {"field": "category.l2", "size": 20},
                        "aggs": {"l3": {"terms": {"field": "category.l3", "size": 30}}},
                    }
                },
            },
            "inventory_status": {"terms": {"field": "inventory_status", "size": 10}},
        },
    }

    # print('ES Query:',body)
    results = es.search(index=INDEX_NAME, body=body)
    return (results, query)


# -----------------------------
# Retrever Search Function
# -----------------------------
def search_retriever(query_text):
    retriever = {
        "linear": {
            "rank_window_size": 30,
            "fields": ["title^3", "description", "category.raw^2", "semantic_search"],
            "query": query_text,
            "normalizer": "minmax",
        }
    }
    body = {
        "size": 30,
        "retriever": retriever,
        "aggs": {
            "attributes": {
                "nested": {"path": "attributes"},
                "aggs": {
                    "by_name": {
                        "terms": {"field": "attributes.name", "size": 3},
                        "aggs": {
                            "by_value": {
                                "terms": {"field": "attributes.value", "size": 3}
                            }
                        },
                    }
                },
            },
            "l1": {
                "terms": {"field": "category.l1", "size": 10},
                "aggs": {
                    "l2": {
                        "terms": {"field": "category.l2", "size": 20},
                        "aggs": {"l3": {"terms": {"field": "category.l3", "size": 30}}},
                    }
                },
            },
            "inventory_status": {"terms": {"field": "inventory_status", "size": 10}},
        },
    }
    print(body)
    # print('ES Query:',body)
    results = es.search(index=INDEX_NAME, body=body)
    return (results, retriever)


# -----------------------------
# Render Results + Collect Attributes
# -----------------------------
def render_search_results(res):
    st.write(f"### Total results: {res['hits']['total']['value']}")

    # Attributes
    st.sidebar.subheader("Attributes")
    for attr in res["aggregations"]["attributes"]["by_name"]["buckets"]:
        name = attr["key"]
        values = [v["key"] for v in attr["by_value"]["buckets"]]
        key = f"attr_{name}"
        if key not in st.session_state:
            st.session_state[key] = "-- Any --"

        st.sidebar.selectbox(name, ["-- Any --"] + values, key=key)

    # Inventory Status Facet
    st.sidebar.subheader("Inventory Status Facet:")
    for b in res["aggregations"]["inventory_status"]["buckets"]:
        st.sidebar.write(f"{b['key']} ({b['doc_count']})")

    # Category Facets
    st.sidebar.subheader("Category Facets")
    for l1_bucket in res["aggregations"]["l1"]["buckets"]:
        st.sidebar.write(f"**{l1_bucket['key']} – {l1_bucket['doc_count']}**")
        for l2_bucket in l1_bucket["l2"]["buckets"]:
            st.sidebar.write(
                f"&nbsp;&nbsp;&nbsp;• {l2_bucket['key']} – {l2_bucket['doc_count']}"
            )
            for l3_bucket in l2_bucket["l3"]["buckets"]:
                st.sidebar.write(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- {l3_bucket['key']} – {l3_bucket['doc_count']}"
                )

    # Render Search Results
    for hit in res["hits"]["hits"]:
        src = hit["_source"]
        st.subheader(src.get("title", ""))
        if "category" in src and "raw" in src["category"]:
            st.write("**Category:** " + src["category"]["raw"])
        st.write(f"**Inventory:** {src.get('inventory_status')}")
        st.write(f"**Supplier Rating:** {src.get('supplier_rating', '—')}")
        st.write(f"**Description:** {src.get('description', '—')}")
        attributes = src.get("attributes", [])
        if attributes:
            st.write("**Attributes:**")
            for a in attributes:
                st.write(f"- {a['name']}: {a['value']}")
        st.write("---")


# -----------------------------
# Main Application Logic
# -----------------------------

# Fetch category hierarchy for filters
agg_query = {
    "size": 0,
    "aggs": {
        "l1": {
            "terms": {"field": "category.l1", "size": 100},
            "aggs": {
                "l2": {
                    "terms": {"field": "category.l2", "size": 200},
                    "aggs": {"l3": {"terms": {"field": "category.l3", "size": 300}}},
                }
            },
        }
    },
}

agg_res = es.search(index=INDEX_NAME, body=agg_query)
category_hierarchy = {}
for l1_bucket in agg_res["aggregations"]["l1"]["buckets"]:
    l1_name = l1_bucket["key"]
    category_hierarchy[l1_name] = {}

    for l2_bucket in l1_bucket["l2"]["buckets"]:
        l2_name = l2_bucket["key"]

        category_hierarchy[l1_name][l2_name] = [
            l3_bucket["key"] for l3_bucket in l2_bucket["l3"]["buckets"]
        ]


# Initialize persistent state variables
if "query" not in st.session_state:
    st.session_state["query"] = ""
query_input = st.text_input("Search products:")

# --- UI – Sidebar Filters ---

st.sidebar.header("Filters")
l1 = st.sidebar.selectbox(
    "Category Level 1", ["(Any)"] + list(category_hierarchy.keys())
)
l2 = st.sidebar.selectbox(
    "Category Level 2",
    ["(Any)"] + (list(category_hierarchy[l1].keys()) if l1 != "(Any)" else []),
)
l3 = st.sidebar.selectbox(
    "Category Level 3",
    ["(Any)"] + (category_hierarchy[l1][l2] if l1 != "(Any)" and l2 != "(Any)" else []),
)
inv_filter_selections = st.sidebar.multiselect(
    "Inventory", ["in_stock", "out_of_stock"]
)


def execute_search_callback():
    """Triggered when the search button is clicked."""
    st.session_state["query"] = query_input

st.button("Search for products", on_click=execute_search_callback)


# --- Main Logic Execution Block ---

if st.session_state["query"]:

    # 1. Build Base Filters from sidebar selections (l1, l2, l3, inventory)
    base_filters = []
    if l1 != "(Any)":
        base_filters.append({"term": {"category.l1": l1}})
    if l2 != "(Any)":
        base_filters.append({"term": {"category.l2": l2}})
    if l3 != "(Any)":
        base_filters.append({"term": {"category.l3": l3}})
    if inv_filter_selections:
        base_filters.append({"terms": {"inventory_status": inv_filter_selections}})

    # 2. Build Attribute Filters from st.session_state
    current_attribute_selections = {}
    for key, value in st.session_state.items():
        if key.startswith("attr_") and value != "-- Any --":
            attr_name = key[len("attr_") :]
            current_attribute_selections[attr_name] = value

    attribute_filters_list = build_attribute_filter(current_attribute_selections)

    # 3. add attribute filters
    all_filters_to_apply = base_filters + attribute_filters_list

    # 4. Execute the search
    if len(all_filters_to_apply) == 0:
        query_text = st.session_state["query"]
        res = search_retriever(query_text)
        st.write("Search Query:", res[1])
        # 5. Render results
        render_search_results(res[0])
    elif len(all_filters_to_apply) > 0 and st.session_state["query"] == "":
        res = search_filters(all_filters_to_apply)
        st.write("Search Query:", res[1])
        # 5. Render results
        render_search_results(res[0])
    else:
        res = search_hybrid(st.session_state["query"], all_filters_to_apply)
        st.write("Search Query:", res[1])
        # 5. Render results
        render_search_results(res[0])
