import vitis,inspect
client=vitis.create_client()
print('CREATE_PLATFORM',inspect.signature(client.create_platform_component))
print('CREATE_APP',inspect.signature(client.create_app_component))
print('VITIS_CLIENT_READY')
vitis.dispose()
