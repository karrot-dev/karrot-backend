#!/bin/sh

function mod() {
  from=$1
  to=$2
  dir=${3:-"foodsaving config grafana"}
  for d in $dir; do
    echo codemod -m --accept-all -d $d --extensions py,json,mjml "$from" "$to"
    codemod \
      -m \
      --accept-all \
      -d $d \
      --extensions py,json,mjml \
      --exclude-paths foodsaving/management/commands \
      "$from" \
      "$to"
  done
}

if [ -d foodsaving/stores ]; then
  if [ -d foodsaving/places ]; then
    echo "Oops foodsaving/places already exists, please remove it!"
    exit 1
  fi
  mv foodsaving/stores foodsaving/places
fi

for f in $(find foodsaving/*/migrations/*.py | grep store); do
  fnew=$(echo $f | sed 's/_store_/_place_/g')
  mv "$f" "$fnew"
done

mod '_store_' '_place_'
mod '_stores_' '_places_'
mod '\bstore_' 'place_'
mod '_store\b' '_place'
mod '_stores\b' '_places'
mod '\bStore\b' 'Place'
mod '([a-z])Store([A-Z])' '\1Place\2'
mod '([a-z])Store\b' '\1Place'
mod '\bStore([A-Z])' 'Place\1'
mod '([a-z])Stores([A-Z])' '\1Places\2'
mod '\bStores([A-Z])' 'Places\1'
mod '([a-z])Stores\b' '\1Places'
mod '\bstore\b' 'place'
mod '\bstore2\b' 'place2'
mod '\bstores\b' 'places'
mod '\bStores\b' 'Places'
mod 'NEW_STORE' 'NEW_PLACE'

# correct some overmodding
mod 'place_url=place_url\(' 'store_url=place_url('
mod 'place_name=feedback' 'store_name=feedback'
mod '{{ place_url }}' '{{ store_url }}'
mod '{{ place_name }}' '{{ store_name }}'

sed -i 's/group, places and pickup dates/group, stores and pickup dates/' foodsaving/groups/templates/user_became_editor.mjml


mod 'place_true' 'store_true' foodsaving/management/commands
