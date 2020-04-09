import axios from 'axios'

export default axios.create({
  baseURL: process.server ? 'http://127.0.0.1:8080/' : `http://${location.host}/`
})
