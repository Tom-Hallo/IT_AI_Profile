const oldRoute = window.location.hash.slice(1)
const route = oldRoute.startsWith('/') && !oldRoute.startsWith('//') ? oldRoute : '/'
const target = new URL(window.location.origin)
const fragmentUrl = new URL(window.location.origin + route)
target.pathname = fragmentUrl.pathname
target.search = fragmentUrl.search || window.location.search
target.hash = fragmentUrl.hash
window.location.replace(target)
