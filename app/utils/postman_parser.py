import json

def parse_postman_collection(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        collection = json.load(f)

    grouped_items = {}

    def extract_items(item_list, parent_name="Default"):
        for item in item_list:
            if 'item' in item:
                group_name = item.get("name", parent_name)
                extract_items(item['item'], group_name)  # recursive call with folder name
            else:
                request = item.get('request', {})
                url = request.get('url', {})
                headers = request.get('header', [])
                body = request.get('body', {}).get('raw', '')
                method = request.get('method', 'GET')

                full_url = url if isinstance(url, str) else url.get('raw', '')

                req_data = {
                    "name": item.get("name", "Unnamed Request"),
                    "url": full_url,
                    "method": method,
                    "headers": headers,
                    "body": body
                }

                grouped_items.setdefault(parent_name, []).append(req_data)

    extract_items(collection.get('item', []))
    return {"transactions": grouped_items}