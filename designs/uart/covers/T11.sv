// tvalid raised mid-frame (data bits, bit_cnt 1..8) with tdata 8'h3C held
// until loaded; the following frame must shift out 8'h3C.
module cov_T11 (
  input logic        clk,
  input logic        rst,
  input logic        s_axis_tvalid,
  input logic [7:0]  s_axis_tdata,
  input logic        busy,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        txd
);

  reg       tv_q;
  reg [1:0] st;     // 0 idle, 1 armed (waiting for load), 2 shifting
  reg [7:0] shift;
  reg       done;

  always @(posedge clk) begin
    if (rst) begin
      tv_q  <= 1'b0;
      st    <= 2'd0;
      shift <= 8'h00;
      done  <= 1'b0;
    end else begin
      tv_q <= s_axis_tvalid;
      done <= 1'b0;
      if (st == 2'd0) begin
        if (s_axis_tvalid && !tv_q && busy && bit_cnt >= 4'd1 && bit_cnt <= 4'd8 &&
            s_axis_tdata == 8'h3C) begin
          st <= 2'd1;
        end
      end else if (st == 2'd1) begin
        if (!s_axis_tvalid || s_axis_tdata != 8'h3C) begin
          st <= 2'd0;
        end else if (prescale_reg == 19'd0 && bit_cnt == 4'd0) begin
          st    <= 2'd2;
          shift <= 8'h00;
        end
      end else begin
        if (prescale_reg == 19'd0 && bit_cnt >= 4'd1 && bit_cnt <= 4'd8) begin
          shift <= {txd, shift[7:1]};
          if (bit_cnt == 4'd1) begin
            done <= 1'b1;
            st   <= 2'd0;
          end
        end
      end
    end
  end

  T11_tvalid_rise_mid_frame: cover property (@(posedge clk) disable iff (rst)
    done && shift == 8'h3C);

endmodule

bind uart_tx cov_T11 u_cov_T11 (.*);
