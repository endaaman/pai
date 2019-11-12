const fs =  require('fs').promises
const path = require('path')
// const http = require('http')
const WebSocket = require('ws')
const Koa = require('koa')
const Router = require('@koa/router')
const fns = require('date-fns')
const koaBody = require('koa-body')
const multer = require('@koa/multer')


const API_PORT = 8080
const WS_PORT = 8081
const UPLOAD_DIR = 'uploaded/'

const wss = new WebSocket.Server({ port: WS_PORT })
const app = new Koa()
const router = new Router()
const upload = multer()


class Status {
  constructor() {
    this.current = null
  }
  to_json() {
    return JSON.stringify({
      current: this.current,
    })
  }
}



function generate_id() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function get_path(id) {
 return path.join(UPLOAD_DIR, id + '.jpg')
}

const status = new Status()

wss.on('connection', (ws, socket, request) => {
  ws.on('message', (message) => {
    // console.log('received: %s', message)
    ws.send(status.to_json())
  })
})

router.get('/images', async (ctx, next) => {
  console.log('get images')
  ctx.body = 'images'
})

router.post(
  '/upload',
  upload.single('image'),
  async (ctx, next) => {
    console.log('ctx.file', ctx.file)
    console.log(ctx.file.buffer)
    const i = generate_id()
    const p = get_path(i)
    await fs.writeFile(p, ctx.file.buffer)
    ctx.body = 'up'
    console.log('wrote: ', p)
  }
)

app.use(router.routes())
app.use(router.allowedMethods())
app.use(koaBody({ multipart: true }))
app.listen(API_PORT, () => {
    console.log('Started')
})
