import aria.ops.adapter_logging as logging

logger = logging.getLogger(__name__)

def lookup_resource(ops_client, query, identifiers = None):
    response = ops_client.post("/resources/query", json=query)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code}: {response.text}")
    resource_list = response.json()["resourceList"]

    filtered_resource_list = []
    if identifiers:
        for resource in resource_list:
            include = True
            for id in identifiers:
                for res_id in resource["resourceKey"]["resourceIdentifiers"]:
                    if res_id["identifierType"]["name"] == id.key and res_id["value"] != id.value:
                        include = False
                        break
            if include:
                filtered_resource_list.append(resource)
    else:
        filtered_resource_list = resource_list
    if len(filtered_resource_list) == 0:
        logger.warning(f"Resource was not found. Skipping!")
        return None
    if len(filtered_resource_list) > 1:
        logger.warning(f"More than one resource found. Defaulting to first in list")
    return filtered_resource_list[0]

def set_parent(ops_client, child, parent):
    payload = { "uuids": [ parent ]}
    response = ops_client.post(f"/resources/{child}/relationships/parents", json=payload)
    if response.status_code != 204:
        raise Exception(f"API Error: {response.status_code}: {response.text}")