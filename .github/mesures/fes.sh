# Fa una ordre i en desa la sortida en un fitxer, sense canonades: a Windows, un procés fill que seguís viu
# deixaria la canonada oberta i el pas de GitHub no acabaria mai.
#   fes resultats/x.log ordre arguments…
fes() {
  local fitxer="$1"
  shift
  local codi=0
  "$@" < /dev/null > "$fitxer" 2>&1 || codi=$?
  echo "[$codi] $fitxer"
  tail -3 "$fitxer" | cut -c1-500
  return 0
}
