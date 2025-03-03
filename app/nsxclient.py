import requests
import urllib.parse

class NSXClient:
    url_base = ""
    xsrf_token = ""
    session = requests.Session()

    def __init__(self, host):
        self.url_base = "https://" + host + "/api"

    def get(self, url):
        response = self.session.get(self.url_base + url, headers={ "Accept": "application/json", "x-xsrf-token": self.xsrf_token}, verify=False)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code}: {response.text}")
        return response.json()

    def get_transport_nodes(self):
        return self.get("/v1/transport-nodes")

    def get_transport_node_status(self, node_id):
        return self.get(f"/v1/transport-nodes/{node_id}/status")

    def get_transport_node_cpu_status(self, node_id):
        return self.get(f"/v1/transport-nodes/{node_id}/node/services/dataplane/cpu-stats")

    def authenticate(self, username, password):
        payload = f"j_username={urllib.parse.quote_plus(username)}&j_password={urllib.parse.quote_plus(password)}"
        response = self.session.post(self.url_base + "/session/create", data=payload, headers={ "Content-Type": "application/x-www-form-urlencoded" }, verify=False)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code}: {response.text}")
        self.xsrf_token = response.headers.get("x-xsrf-token")


client = NSXClient("nsx-mgmt.vcf.sddc.lab")
client.authenticate("admin", "VMware123!VMware123!")
transport_nodes = client.get_transport_nodes()
for node in transport_nodes["results"]:
    node_id = node["id"]

    # Collect general node stats
    node_stats = client.get_transport_node_status(node_id)
    system_status = node_stats["node_status"]["system_status"]

    # Skip ESXi nodes
    if "datapath_mem_usage_details" not in system_status["edge_mem_usage"]:
        continue

    cpu_cores = system_status["cpu_cores"]
    mem_used = system_status["mem_used"]
    datapath_memory = system_status["edge_mem_usage"]["datapath_mem_usage_details"]
    highest_datapath_mem_usage = datapath_memory["highest_datapath_mem_pool_usage"]
    for pool in datapath_memory["datapath_mem_pools_usage"]:
        if pool["name"] == "mbuf_pool_socket_0":
            mbuf_pool_socket_0 = pool["usage"]

    # Collect node CPU specifics
    cpu_stats = client.get_transport_node_cpu_status(node_id)
    for core_stats in cpu_stats["cores"]:
        print(core_stats["core"], core_stats["cpu_type"], core_stats["usage"])
    print(cpu_stats)
print(transport_nodes)
