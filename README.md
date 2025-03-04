# Sample SDK-Based NSX Management Pack

This is a sample management pack for collection of custom NSX metrics.

## How to buil
1. Install the Aria Operations Management Pack SDK
2. Change the "container_repository" in config.json to point to a repository where you have write access.
3. Run the `mp-build` command.

To test the management pack without a full build, use the `mp-test` command.

Full documentation of the SDK can be found here: https://vmware.github.io/vmware-aria-operations-integration-sdk/sdk/latest/
