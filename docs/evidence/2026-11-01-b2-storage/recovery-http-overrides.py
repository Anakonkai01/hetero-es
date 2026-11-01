@app.post('/api/v1/artifacts/{artifact_id}/download-ticket')
def ticket(artifact_id: str, response: Response, request: Request, current=Depends(scoped)):
    result = service.ticket(artifact_id=artifact_id, token=request.headers.get('Authorization', '')[7:], current=current)
    path = result['downloadUrl']
    response.set_cookie('heteroes-cloud-download', result['secret'], httponly=True, secure=request.url.scheme == 'https', samesite='strict', path=path, max_age=60)
    return {'downloadUrl': path}

@app.get('/api/v1/cloud-downloads/{ticket_digest}')
def consume(ticket_digest: str, request: Request):
    url = service.consume(ticket_digest=ticket_digest, secret=request.cookies.get('heteroes-cloud-download', ''))
    response = RedirectResponse(url, status_code=303)
    response.delete_cookie('heteroes-cloud-download', path='/api/v1/cloud-downloads/' + ticket_digest)
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
