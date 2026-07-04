from googlesearch import search
results = search("test query", advanced=True, num_results=5)
for r in results:
    print(r.title, r.url, r.description)
