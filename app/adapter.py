#  Copyright 2022 VMware, Inc.
#  SPDX-License-Identifier: Apache-2.0
import sys
from typing import List

import aria.ops.adapter_logging as logging
from aria.ops.adapter_instance import AdapterInstance
from aria.ops.data import Metric
from aria.ops.data import Property
from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.definition.units import Units
from aria.ops.object import Identifier
from aria.ops.result import CollectResult
from aria.ops.result import EndpointResult
from aria.ops.result import TestResult
from aria.ops.timer import Timer

from constants import (MEM_USED_KEY, TRANSPORT_NODE_KEY, CORE_COUNT_KEY, MBUF_POOL_MEM_KEY, HIGHEST_DATAPATH_USAGE_KEY,
                       TRANSPORT_NODE_CPU_KEY, USAGE_KEY, CORE_TYPE_KEY, NATIVE_RESOURCE_KIND, NATIVE_ADAPTER_KIND)
from constants import ADAPTER_KIND
from constants import ADAPTER_NAME
from nsxclient import NSXClient
from ops_helper import lookup_resource, set_parent

logger = logging.getLogger(__name__)


def get_adapter_definition() -> AdapterDefinition:
    """
    The adapter definition defines the object types and attribute types (metric/property) that are present
    in a collection. Setting these object types and attribute types helps VMware Aria Operations to
    validate, process, and display the data correctly.
    :return: AdapterDefinition
    """
    with Timer(logger, "Get Adapter Definition"):
        definition = AdapterDefinition(ADAPTER_KIND, ADAPTER_NAME)

        credential = definition.define_credential_type("credential", "NSX Manager Credential")
        credential.define_string_parameter("username", "Username")
        credential.define_password_parameter("password", "Password")

        definition.define_string_parameter(
            "host",
            label="NSX Host",
            description="FWDN or IP address of the NSX Manager to monitor",
            required=True
        )
        # The key 'container_memory_limit' is a special key that is read by the VMware Aria Operations collector to
        # determine how much memory to allocate to the docker container running this adapter. It does not
        # need to be read inside the adapter code.
        definition.define_int_parameter(
            "container_memory_limit",
            label="Adapter Memory Limit (MB)",
            description="Sets the maximum amount of memory VMware Aria Operations can "
            "allocate to the container running this adapter instance.",
            required=True,
            advanced=True,
            default=1024,
        )

        # Transport Node resource
        node = definition.define_object_type(TRANSPORT_NODE_KEY, "NSX Transport Node")
        node.define_numeric_property(CORE_COUNT_KEY, "Core Count", is_discrete=True)
        node.define_string_identifier("nsxId", "NSX ID", True)
        node.define_metric(MEM_USED_KEY, "Memory Usage", Units.DATA_SIZE.KILOBYTE)
        node.define_metric(MBUF_POOL_MEM_KEY, MBUF_POOL_MEM_KEY, Units.DATA_SIZE.KILOBYTE)
        node.define_metric(HIGHEST_DATAPATH_USAGE_KEY, "Top Datapath Pool Usage", Units.DATA_SIZE.KILOBYTE)
        core = node.define_instanced_group("core", "Core", True)
        core.define_metric(USAGE_KEY, "Usage", Units.RATIO.PERCENT)
        core.define_string_property(CORE_TYPE_KEY, "Core type")

        # Transport Node CPU resource
        node_cpu = definition.define_object_type(TRANSPORT_NODE_CPU_KEY, "NSX Transport CPU")
        node_cpu.define_metric(USAGE_KEY, "Usage")
        node_cpu.define_string_property(CORE_TYPE_KEY, "Core Type")
        logger.debug(f"Returning adapter definition: {definition.to_json()}")
        return definition

def get_client(adapter_instance):
    host = adapter_instance.get_identifier_value("host")
    username = adapter_instance.get_credential_value("username")
    password = adapter_instance.get_credential_value("password")
    nsx = NSXClient(host)
    nsx.authenticate(username, password)
    return nsx


def test(adapter_instance: AdapterInstance) -> TestResult:
    with Timer(logger, "Test"):
        result = TestResult()
        try:
            nsx = get_client(adapter_instance)
            nodes = nsx.get_transport_nodes()
            if not nodes:
                result.with_error("Get transport node API call returned null")
        except Exception as e:
            logger.error("Unexpected connection test error")
            logger.exception(e)
            result.with_error("Unexpected connection test error: " + repr(e))
        finally:
            # TODO: If any connections are still open, make sure they are closed before returning
            logger.debug(f"Returning test result: {result.get_json()}")
            return result

def collect(adapter_instance: AdapterInstance) -> CollectResult:
    with Timer(logger, "Collection"):
        result = CollectResult()
        try:
            with adapter_instance.get_suite_api_client() as ops_client:
                client = get_client(adapter_instance)
                transport_nodes = client.get_transport_nodes()
                for node in transport_nodes["results"]:
                    node_id = node["id"]
                    node_name = node["display_name"]

                    query = {
                        "name": [node_name],
                        "adapterKind": [ADAPTER_KIND],
                        "resourceKind": [TRANSPORT_NODE_KEY],
                    }

                    # Custom resource already created
                    current_node = lookup_resource(ops_client, query)
                    if current_node:
                        query = {
                            "name": [node_name],
                            "adapterKind": [NATIVE_ADAPTER_KIND],
                            "resourceKind": [NATIVE_RESOURCE_KIND],
                        }

                        # Lookup parent (native) node
                        identifiers = [Identifier("ID", node_id)]
                        parent_node = lookup_resource(ops_client, query, identifiers)
                        if parent_node:
                            set_parent(ops_client, current_node["identifier"], parent_node["identifier"])
                        else:
                            raise Exception("Parent not found")

                    # Collect general node stats
                    node_stats = client.get_transport_node_status(node_id)
                    system_status = node_stats["node_status"]["system_status"]

                    # Skip ESXi nodes
                    if "datapath_mem_usage_details" not in system_status["edge_mem_usage"]:
                        continue

                    node_name = node["display_name"]
                    identifiers = [Identifier("nsxId", node["id"], True)]
                    node_result = result.object(ADAPTER_KIND, TRANSPORT_NODE_KEY, node_name, identifiers)

                    node_result.add_metric(Metric(MEM_USED_KEY, system_status[MEM_USED_KEY]))
                    node_result.add_property(Property(CORE_COUNT_KEY, system_status[CORE_COUNT_KEY]))

                    datapath_memory = system_status["edge_mem_usage"]["datapath_mem_usage_details"]
                    node_result.add_metric(Metric(HIGHEST_DATAPATH_USAGE_KEY, datapath_memory[HIGHEST_DATAPATH_USAGE_KEY]))
                    for pool in datapath_memory["datapath_mem_pools_usage"]:
                        if pool["name"] == "mbuf_pool_socket_0":
                            node_result.add_metric(Metric(MBUF_POOL_MEM_KEY, pool["usage"]))

                    # Collect node CPU specifics
                    cpu_stats = client.get_transport_node_cpu_status(node_id)
                    for core_stats in cpu_stats["cores"]:
                        core_num = core_stats["core"]
                        node_result.add_metric(Metric(f"core|{core_num}|usage", core_stats["usage"]))
                        node_result.add_property(Property(f"core|{core_num}|core_type", core_stats["cpu_type"]))

                        # Alternative method: Create child object
                        node_cpu = result.object(ADAPTER_KIND, TRANSPORT_NODE_CPU_KEY, f"{node_name}:{core_num}")
                        node_cpu.add_metric(Metric(USAGE_KEY, core_stats["usage"]))
                        node_cpu.add_property(Property(CORE_TYPE_KEY, core_stats["cpu_type"]))
                        node_result.add_child(node_cpu)

        except Exception as e:
            logger.error("Unexpected collection error")
            logger.exception(e)
            result.with_error("Unexpected collection error: " + repr(e))
        finally:
            # TODO: If any connections are still open, make sure they are closed before returning
            logger.debug(f"Returning collection result {result.get_json()}")
            return result


def get_endpoints(adapter_instance: AdapterInstance) -> EndpointResult:
    with Timer(logger, "Get Endpoints"):
        result = EndpointResult()
        # In the case that an SSL Certificate is needed to communicate to the target,
        # add each URL that the adapter uses here. Often this will be derived from a
        # 'host' parameter in the adapter instance. In this Adapter we don't use any
        # HTTPS connections, so we won't add any. If we did, we might do something like
        # this:
        # result.with_endpoint(adapter_instance.get_identifier_value("host"))
        #
        # Multiple endpoints can be returned, like this:
        # result.with_endpoint(adapter_instance.get_identifier_value("primary_host"))
        # result.with_endpoint(adapter_instance.get_identifier_value("secondary_host"))
        #
        # This 'get_endpoints' method will be run before the 'test' method,
        # and VMware Aria Operations will use the results to extract a certificate from
        # each URL. If the certificate is not trusted by the VMware Aria Operations
        # Trust Store, the user will be prompted to either accept or reject the
        # certificate. If it is accepted, the certificate will be added to the
        # AdapterInstance object that is passed to the 'test' and 'collect' methods.
        # Any certificate that is encountered in those methods should then be validated
        # against the certificate(s) in the AdapterInstance.
        logger.debug(f"Returning endpoints: {result.get_json()}")
        return result


# Main entry point of the adapter. You should not need to modify anything below this line.
def main(argv: List[str]) -> None:
    logging.setup_logging("adapter.log")
    # Start a new log file by calling 'rotate'. By default, the last five calls will be
    # retained. If the logs are not manually rotated, the 'setup_logging' call should be
    # invoked with the 'max_size' parameter set to a reasonable value, e.g.,
    # 10_489_760 (10MB).
    logging.rotate()
    logger.info(f"Running adapter code with arguments: {argv}")
    if len(argv) != 3:
        # `inputfile` and `outputfile` are always automatically appended to the
        # argument list by the server
        logger.error("Arguments must be <method> <inputfile> <ouputfile>")
        sys.exit(1)

    method = argv[0]
    try:
        if method == "test":
            test(AdapterInstance.from_input()).send_results()
        elif method == "endpoint_urls":
            get_endpoints(AdapterInstance.from_input()).send_results()
        elif method == "collect":
            collect(AdapterInstance.from_input()).send_results()
        elif method == "adapter_definition":
            result = get_adapter_definition()
            if type(result) is AdapterDefinition:
                result.send_results()
            else:
                logger.info(
                    "get_adapter_definition method did not return an AdapterDefinition"
                )
                sys.exit(1)
        else:
            logger.error(f"Command {method} not found")
            sys.exit(1)
    finally:
        logger.info(Timer.graph())
        sys.exit(0)

def translate_identifiers(identifiers):
    result = []
    for id in identifiers:
        id_type = id["identifierType"]
        result.append(Identifier(key=id_type["name"], is_part_of_uniqueness=id_type["isPartOfUniqueness"], value=id["value"]))
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
