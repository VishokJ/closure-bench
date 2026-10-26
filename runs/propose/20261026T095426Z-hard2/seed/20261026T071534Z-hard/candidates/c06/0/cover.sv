// A frame at prescale 1 completes. A new frame is then loaded at prescale 3
// while busy is low. Each data bit starts with prescale_reg == 23 (24 clocks
// per bit), and the txd values at the bit starts form 8'h5A.
module cov_P6 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        busy,
  input logic        s_axis_tvalid
);

  // 0: idle; 1: a frame was loaded at prescale 1;
  // 2: the next frame was loaded at prescale 3 with busy low
  reg [1:0] st;
  reg [7:0] shift;

  always @(posedge clk) begin
    if (rst) begin
      st    <= 2'd0;
      shift <= 8'h00;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
        shift <= 8'h00;
        if (prescale == 16'd1) st <= 2'd1;
        else if (st == 2'd1 && !busy && prescale == 16'd3) st <= 2'd2;
        else st <= 2'd0;
      end else begin
        if (st == 2'd1 && busy && prescale != 16'd1) st <= 2'd0;
        if (st == 2'd2) begin
          if (prescale != 16'd3) st <= 2'd0;
          else if (prescale_reg == 19'd23 && bit_cnt >= 4'd2 && bit_cnt <= 4'd8)
            shift <= {txd, shift[7:1]};
        end
      end
    end
  end

  P6_tx_rate_change_5a: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && prescale == 16'd3 && bit_cnt == 4'd1 && prescale_reg == 19'd23 &&
    {txd, shift[7:1]} == 8'h5A);

endmodule

bind uart_tx cov_P6 u_cov_P6 (.*);
