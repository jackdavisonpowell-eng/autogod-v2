# Source this on thebeast to put dsh on PATH under nvm's node 22
# (thebeast's system node is 18.20, too old for dsh's Node >=22.19 requirement).
#
#   ssh thebeast
#   source ~/autogod-v2-bench-dsh-env.sh   # or wherever you've copied this
#   dsh --profile headless "..."
#
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 22 >/dev/null

# The llama.cpp brain (http://127.0.0.1:11466) takes no auth, but dsh's
# pi-ai OpenAI-compatible client still requires *some* API key value to be
# present for the route to be considered "configured". Any placeholder works.
export DSH_LOCAL_API_KEY="local-placeholder"
