const fs =  require('fs').promises
const pathlib = require('path')
const util = require('util')
const childProcess = require('child_process')
// const http = require('http')
const WebSocket = require('ws')
const Koa = require('koa')
const Router = require('@koa/router')
const fns = require('date-fns')
const koaBody = require('koa-body')
const multer = require('@koa/multer')

const exec = util.promisify(childProcess.exec)



const API_PORT = 8080
const WS_PORT = 8081
const UPLOAD_DIR = 'uploaded/'
const GENERATED_DIR = 'generated/'

const wss = new WebSocket.Server({ port: WS_PORT })
const koa = new Koa()
const router = new Router()
const upload = multer()

function generate_id() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function get_uploaded_path(id) {
  return pathlib.join(UPLOAD_DIR, id + '.jpg')
}

function get_generated_dir(id) {
  return pathlib.join(GENERATED_DIR, id + '.jpg')
}

async function do_inference(id) {
  await exec(`bash scripts/fake.sh ${id}.jpg`)
}

function wait(s) {
  return new Promise(function (r) {
    setTimeout(r, s)
  })
}

class App {
  constructor() {
    this.queue = []
    this.task = Promise.resolve()
    this.current = null
  }
  to_json() {
    return JSON.stringify({
      queue: this.queue,
      current: this.current,
    })
  }
  push_task(id) {
    this.queue.push(id)
    this.task = this.task.catch(function(e) {
      console.log(`ERROR: ${e}`)
    }).then(async () => {
      this.current = this.queue[0]
      await do_inference(this.current)
      await wait(1)
      this.current = null
      this.queue.shift()
      console.log('DONE:', this.queue)
    })
    console.log('CUR: ', this.queue)
  }
}


const app = new App()

wss.on('connection', (ws, socket, request) => {
  console.log('Connected')
  ws.on('message', (message) => {
    // console.log('received: %s', message)
    ws.send(app.to_json())
  })
})

router.get('/api/images', async (ctx, next) => {
  console.log('get images')
  ctx.body = 'images'
})

router.post(
  '/api/upload',
  upload.single('image'),
  async (ctx, next) => {
    const id = generate_id()
    const p = get_uploaded_path(id)
    await fs.writeFile(p, ctx.file.buffer)
    app.push_task(id)
    ctx.body = 'up'
    console.log('wrote: ', p)
  }
)

koa.use(router.routes())
koa.use(router.allowedMethods())
koa.use(koaBody({ multipart: true }))
koa.listen(API_PORT, () => {
    console.log('Started')
})
