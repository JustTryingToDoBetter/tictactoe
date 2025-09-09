import socket

## create server 

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM) ## object

server.bind(('127.0.01', 12345)) ## bind
server.listen(1) #listen for in comming connection
print('server is listening')

conn, addr = server.accept() ## conncection
print(f'connected by {addr}')

data = conn.recv(1024) ## receive data
print(f'receieve: {data.decode()}')

conn.sendall(b'hello, client') ## send response
conn.close() ## close connection

















def new_board():

    return [[None,None,None],
            [None,None,None],
            [None,None,None]]

def get_move():
    while True:
        x = int(input("what is your x coordinate(0-2): "))
        if type(x) != int:
            print("Mmmmmmmm seems like you did not input a number")
        
        y = int(input("what is your y coordinate(0-2): "))
        if type(y) != int:
            print("Mmmmmmmm seems like you did not input a number") 
        if 0 <= x <= 2 and 0 <= y <= 2:
            break
        else:
            print("Mmmmmmm seems like you giving values greater than 2 or less than 0")  
    return x, y


def is_valid_move(board, coords):
    x, y = coords
    if board[x][y] != None:
        return False
    else:
        return True

def make_move(board, coord, move):
    if is_valid_move(board, coord) == False:
        print("ajjajajajjaja")
    else:
        row, col = coord
        board[row][col] = move
        return board
def render(board):
    for r in board:
        display_row = [cell if cell is not None else " " for cell in r]
        print(" | ".join(display_row))
        print(" " * 2 + "-" * 5)


def check_winner(board, player):
    for row in board:
        if player == row[0] == row[1] == row[2]:
            print(f"{player} wins")
            return True
    for col in range(3):
        if board[0][col] ==  board[1][col] ==  board[2][col] == player:
            print(f"{player} wins")
            return True

    if board[0][0] == board[1][1] == board[2][2] == player:
        print(f"{player} wins")
        return True
    if board[0][2] == board[1][1] == board[2][0] == player:
        print(f"{player} wins")
        return True
    
    return False  


def is_full(board):
    for r in board:
        for c in r:
            if c is None:
                return False
    return True

def player_tracking():
    turn = 1
    board = new_board()
    render(board)
    while True:
        if turn == 1:
            print("Player one turn")
            coord = get_move()
            tmp_board = make_move(board, coord, 'X')
            print(render(tmp_board))
            board = tmp_board 
            turn += 1
            if check_winner(board, "X"):
                break
        elif turn == 2:
            print("Player two turn")
            coord = get_move()
            tmp_board = make_move(board, coord,'O')
            print(render(tmp_board))
            board = tmp_board 
            turn -= 1
            if check_winner(board, "X"):
                break
        if is_full(tmp_board) == True:
            break

print(player_tracking())


   


