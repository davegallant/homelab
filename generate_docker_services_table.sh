#!/usr/bin/env bash

# Script to generate a Markdown table of Docker services and their versions
# from all docker-compose.yml files in the current directory and subdirectories.

echo "| Image | Version |"
echo "|-------|---------|"

# Find all docker-compose.yml files tracked by Git and process them
git ls-files | grep "docker-compose.yml$" | while read -r compose_file; do
  # Extract services and their images
  services=$(yq eval '.services' "$compose_file" 2>/dev/null)
  if [[ -z "$services" ]]; then
    echo "Warning: No services found in $compose_file. Skipping..."
    continue
  fi

  # Extract services and their images
  services=$(yq eval '.services' "$compose_file" 2>/dev/null)

  # Iterate over each service
  yq eval '.services | keys' "$compose_file" | sed 's/^- //' | while read -r service; do
    if [[ -z "$service" ]]; then
      echo "Warning: Empty service name found in $compose_file. Skipping..."
      continue
    fi

    # Extract the image for the service
    image=$(yq eval ".services.$service.image" "$compose_file" 2>/dev/null)
    if [[ -n "$image" ]]; then
      # Extract version from the image tag (if available)
      version=$(echo "$image" | awk -F':' '{print $2}')
      version=${version:-"latest"} # Default to "latest" if no version is specified
      # Strip the tag from the image
      image=$(echo "$image" | awk -F':' '{print $1}')
      # Append to the Markdown table if the image is not already listed
      if ! grep -q "| $image | $version |" <<< "$(cat)"; then
        echo "| $image | $version |"
      fi
    else
      echo "Warning: No image found for service '$service' in $compose_file. Skipping..."
    fi
  done
  # Sort the output alphabetically by the image name
done | sort
