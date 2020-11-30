import httpx
import json
import logging
import redis
import time
import yaml

with open("/app/config.yml", "r") as config_file:
    cfg = yaml.safe_load(config_file)
logging.basicConfig(format='%(asctime)s -- %(levelname)s -- %(message)s')
logging.getLogger().setLevel(logging.DEBUG)
r = redis.Redis(host='redis')
# ETH2_API is the Eth2 beacon node's HTTP endpoint
ETH2_API = cfg["eth2_api"]
SECONDS_PER_SLOT = 12
SLOTS_PER_EPOCH = 32


def pp(j):
    print(json.dumps(j, indent=4))


def query_eth2_api(endpoint):
    url = ETH2_API + endpoint
    logging.debug(f"Calling Eth2 API at endpoint: {url}")
    response = httpx.get(url, timeout=100)
    if response.status_code != 200:
        raise Exception(
            f"GET {url} returned with status code {response.status_code}"
            f" and message {response.json()['message']}"
        )
    response_json = response.json()
    response_data = response_json["data"]
    return response_data


def cache_get_genesis_time():
    cache_genesis_time_bytes = r.get("genesis_time")
    if cache_genesis_time_bytes is not None:
        genesis_time = int(cache_genesis_time_bytes.decode("utf-8"))
        logging.debug(f"Found genesis_time in cache: {genesis_time}")
        return genesis_time
    genesis = query_eth2_api("/eth/v1/beacon/genesis")
    genesis_time = int(genesis["genesis_time"])
    logging.info(f"Initializing genesis time in cache: {genesis_time}")
    r.set("genesis_time", genesis_time)
    return genesis_time


def get_current_slot():
    genesis_time = cache_get_genesis_time()
    current_time = int(time.time())
    if current_time < genesis_time:
        return -1
    return (current_time - genesis_time)//SECONDS_PER_SLOT


def cache_get_total_balance(finalized_epoch):
    cache_total_balance_bytes = r.get("total_balance")
    if cache_total_balance_bytes is not None:
        cache_total_balance = json.loads(cache_total_balance_bytes.decode('utf-8'))
        logging.debug(f"Found total_balance in cache: {cache_total_balance}")
        if finalized_epoch == cache_total_balance["epoch"]:
            logging.debug(f"Epoch for query matches cached epoch for total balance: {finalized_epoch}")
            return cache_total_balance["total_balance"]
    logging.info("No valid cache for total_balance, fetching from Eth2 API")
    validators = query_eth2_api("/eth/v1/beacon/states/finalized/validators")
    total_balance = 0
    for validator in validators:
        if validator["status"].lower().startswith("active"):
            total_balance += (
                float(validator["validator"]["effective_balance"])/10**9
            )
    cache_total_balance = {"epoch": finalized_epoch, "total_balance": total_balance}
    r.set("total_balance", json.dumps(cache_total_balance))
    logging.info(f"Refreshed total_balance in cache: {cache_total_balance}")
    return cache_total_balance["total_balance"]


def cache_get_fork_choice_data():
    fork_choice_data_bytes = r.get("fork_choice_data")
    if fork_choice_data_bytes is not None:
        fork_choice_data = json.loads(fork_choice_data_bytes.decode("utf-8"))
        logging.debug(f'Found fork_choice_data in cache, with slot: {fork_choice_data["current_slot"]}')
        current_slot = get_current_slot()
        if current_slot == fork_choice_data["current_slot"]:
            logging.debug("Found valid fork_choice_data in cache")
            return fork_choice_data
    logging.info("No valid cache for fork_choice_data, refreshing now")

    current_slot = get_current_slot()
    if current_slot < 0:
        logging.info("Genesis has not happened yet!")
        return {
            "current_slot": -1,
            "proto_array": {},
            "total_balance": 0,
            "current_head": None,
            "finality_checkpoints": None
        }
    head_before = query_eth2_api("/eth/v1/beacon/headers/head")
    finality_checkpoints = query_eth2_api("/eth/v1/beacon/states/head/finality_checkpoints")
    finalized_epoch = int(finality_checkpoints["finalized"]["epoch"])
    justified_epoch = int(finality_checkpoints["current_justified"]["epoch"])

    proto_array = query_eth2_api('/lighthouse/proto_array')
    nodes = proto_array['nodes']
    indices = proto_array['indices']
    assert max(indices.values())+1 == len(indices)
    inverted_indices = dict(map(reversed, indices.items()))
    nodes_map = {}
    for node in nodes:
        nodes_map[node["root"]] = node

    children = {}
    children[None] = []
    for i in range(len(indices)):
        children[i] = []
    for node in nodes:
        parent_index = node["parent"]
        node_index = indices[node["root"]]
        children[parent_index].append(node_index)

    def build_tree_node(node_index):
        block_root = inverted_indices[node_index]
        node = nodes_map[block_root]
        node["index"] = node_index
        node["weight"] = float(node["weight"])/10**9
        node["children"] = []
        for child_index in children[node_index]:
            node["children"].append(build_tree_node(child_index))
        # Styling
        node["status"] = "pending"
        node["path"] = "noncanonical"
        parent_index = node["parent"]
        if parent_index is not None:
            parent_root = inverted_indices[parent_index]
            parent_node = nodes_map[parent_root]
            if parent_node["best_child"] == node_index:
                node["path"] = "canonical"
                if int(node["slot"]) <= SLOTS_PER_EPOCH * finalized_epoch:
                    node["status"] = "final"
                elif int(node["slot"]) <= SLOTS_PER_EPOCH * justified_epoch:
                    node["status"] = "justified"
        elif int(node["slot"]) <= SLOTS_PER_EPOCH * finalized_epoch:
            node["path"] = "canonical"
            node["status"] = "final"
        return node

    tree_data = build_tree_node(0)

    total_balance = cache_get_total_balance(finalized_epoch)
    head_after = query_eth2_api("/eth/v1/beacon/headers/head")
    if head_before["root"] == head_after["root"]:
        fork_choice_data = {
            "current_slot": current_slot,
            "proto_array": tree_data,
            "total_balance": total_balance,
            "current_head": head_after,
            "finality_checkpoints": finality_checkpoints
        }
        r.set("fork_choice_data", json.dumps(fork_choice_data))
        logging.info(f'Refreshed fork_choice_data in cache at slot: {fork_choice_data["current_slot"]}')
        return fork_choice_data
    else:
        logging.warn("head_before and head_after do not match."
                     f"head_before: {head_before}, head_after: {head_before}")
        return {
            "current_slot": -2,
            "proto_array": {},
            "total_balance": 0,
            "current_head": None,
            "finality_checkpoints": None
        }


def get_fork_choice_data():
    # ----------------------------------------------------------
    # Compute current slot time
    genesis = query_eth2_api("/eth/v1/beacon/genesis")
    genesis_time = int(genesis["genesis_time"])
    if time.time() <= genesis_time:
        return {
            "current_slot": -1,
            "proto_array": {},
            "total_balance": 0,
            "current_head": None,
            "finality_checkpoints": None
        }
    current_slot = (time.time() - genesis_time)//SECONDS_PER_SLOT

    # ----------------------------------------------------------
    # Store the head slot right now
    head_before = query_eth2_api("/eth/v1/beacon/headers/head")

    # ----------------------------------------------------------
    finality_checkpoints = query_eth2_api("/eth/v1/beacon/states/head/finality_checkpoints")
    finalized_epoch = int(finality_checkpoints["finalized"]["epoch"])
    justified_epoch = int(finality_checkpoints["current_justified"]["epoch"])

    # ----------------------------------------------------------
    # Build block tree from proto-array response
    proto_array = query_eth2_api('/lighthouse/proto_array')
    nodes = proto_array['nodes']
    indices = proto_array['indices']
    assert max(indices.values())+1 == len(indices)
    inverted_indices = dict(map(reversed, indices.items()))
    nodes_map = {}
    for node in nodes:
        nodes_map[node["root"]] = node

    children = {}
    children[None] = []
    for i in range(len(indices)):
        children[i] = []
    for node in nodes:
        parent_index = node["parent"]
        node_index = indices[node["root"]]
        children[parent_index].append(node_index)

    def build_tree_node(node_index):
        block_root = inverted_indices[node_index]
        node = nodes_map[block_root]
        node["index"] = node_index
        node["weight"] = float(node["weight"])/10**9
        node["children"] = []
        for child_index in children[node_index]:
            node["children"].append(build_tree_node(child_index))
        # Styling
        node["status"] = "pending"
        node["path"] = "noncanonical"
        parent_index = node["parent"]
        if parent_index is not None:
            parent_root = inverted_indices[parent_index]
            parent_node = nodes_map[parent_root]
            if parent_node["best_child"] == node_index:
                node["path"] = "canonical"
                if int(node["slot"]) <= SLOTS_PER_EPOCH * finalized_epoch:
                    node["status"] = "final"
                elif int(node["slot"]) <= SLOTS_PER_EPOCH * justified_epoch:
                    node["status"] = "justified"
        elif int(node["slot"]) <= SLOTS_PER_EPOCH * finalized_epoch:
            node["path"] = "canonical"
            node["status"] = "final"
        return node

    tree_data = build_tree_node(0)

    # ----------------------------------------------------------
    # Calculate total active balance at finalized state
    validators = query_eth2_api("/eth/v1/beacon/states/finalized/validators")
    total_balance = 0
    for validator in validators:
        if validator["status"].lower().startswith("active"):
            total_balance += (
                float(validator["validator"]["effective_balance"])/10**9
            )

    # ----------------------------------------------------------
    # Check that the fork choice head has not changed while processing
    head_after = query_eth2_api("/eth/v1/beacon/headers/head")
    if head_before["root"] == head_after["root"]:
        return {
            "current_slot": current_slot,
            "proto_array": tree_data,
            "total_balance": total_balance,
            "current_head": head_after,
            "finality_checkpoints": finality_checkpoints
        }
    else:
        logging.warn("head_before and head_after do not match."
                     f"head_before: {head_before}, head_after: {head_before}")
        return get_fork_choice_data()
