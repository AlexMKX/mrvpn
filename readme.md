# The MultiRoute VPN

When the internet split into outernet and innernet, it is not enough to have a VPN to reach the outernet. 
When client vpns the outernet, you don't have access to some innernet sites and vice versa.
The MultiRoute VPN is a tool to solve this.

```mermaid
  graph LR;
      Clients-->MRVPN;
      MRVPN-->InnerNet;
      MRVPN-->OuterNetHost;
      OuterNetHost-->OuterNet;
```

## Routing decisions
The routing decision is made on DNS and IP information. When the client resolves the DNS name for some host, 
the request is intercepted by the recursor. Before sending the answer to the client, the recursor 
decides where the later traffic should go and applies the appropriate routing to the subnet/IP. 
When packets start flowing, they get routed properly. 

Sometimes, when complex CNAME chains are used for the hosts, the routing information is applied 
after the client receives the IP address (ozon.ru is an example). In this case, two possible solutions can be used:

1. Specify IP in the subnets list.
2. Flush DNS cache and retry the navigation.


## Deployment
The MRVPN is deployed as an ansible role. The 2 hosts are needed for the deployment : 
1. Entry point host, which includes:
   1. FireZone (the WireGuard solution)
   2. Docker to server everything:
      1. WireGuard client to the outernet upstream.
      2. IPT Server: the routing decision daemon.
      3. PowerDNS Recursor to handle and hook DNS requests
2. Outernet host with WireGuard daemon.

### Basic deployment config:
```yaml
- hosts: localhost
  tasks:
    - add_host:
        name: entry_point_host
- hosts: entry_point_host
  roles:
    - role: mrvpn
      vars:
        # The entrypoint hostname for FireZone 
        server_url: "mrvpn.mrvpn.host"
        # Wireguard client config from outernet host
        wireguard_config: |
          [Interface]
          PrivateKey = ################
          Address = 10.3.2.16/32
          DNS = 1.1.1.1, 1.0.0.1
          PostUp = iptables -t nat -A POSTROUTING -o wg0 -j MASQUERADE
          PostDown = iptables -t nat -D POSTROUTING -o wg0 -j MASQUERADE
          
          [Peer]
          PublicKey = ################
          PresharedKey = ################
          AllowedIPs = 1.0.0.0/8
          Endpoint = Outernet host ip
          PersistentKeepalive = 25
```
### Prerequisites
1. The debian/ubuntu for the entrypoint host
2. Install ansible requirements with: ```ansible-galaxy install -r requirements.yml```

### Advanced configuration options:

```yaml
# Firezone admin email
firezone_admin: "no@email.com"
# Outernet host subnet where client's IP addresses will be allocated
vpn_subnet: "10.8.2.0/24"
# The IP of the Outernet WireGuard host
vpn_host: "10.8.2.1"
# The docker subnet for infrastructure services
docker_subnet: "10.5.0"
# Routing table num to handle PBR
route_table_num: 11
# Countries which will be routed to the innernet route
countries:
  - 'RU'
  - 'AM'
# Pre-defined regexps of the domains to route them to the innernet
domains:
  - '^.*\.ru$'
  - '^.*ozon\.travel$'
# Also can be fetched from the url
domain_lists:
  - https://raw.githubusercontent.com/AlexMKX/mrvpnconfig/main/domains.txt


# Subnets and hosts to be routed to the innernet
subnets:
  - '195.34.20.248'
# Hosts also can be fetched from the url 
subnet_lists:
  - https://raw.githubusercontent.com/AlexMKX/mrvpnconfig/main/subnets.txt

# Additional firezone config. Probably you want to enable SAML for clients
firezone_config: |
  # default['firezone']['authentication']['google']['enabled'] = false
  # default['firezone']['authentication']['google']['client_id'] = nil
  # default['firezone']['authentication']['google']['client_secret'] = nil
  # default['firezone']['authentication']['google']['redirect_uri'] = nil

# Force FireZone redeploy on each deployment
firezone_redeploy: False

# Where services will reside
target_dir: /srv/mrvpn
```

After role deployment is done, you can find the FireZone credentials in the ```target_dir/firezone_admin_password```
To reset, or, actually, recover admin password - set the firezone_redeploy to True and run role deployment again

