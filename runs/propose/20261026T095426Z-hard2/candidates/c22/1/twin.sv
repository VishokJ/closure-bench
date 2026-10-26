// Twin: the same two words 8'h96 then 8'h69 at prescale 16'd1, but the second
// word is accepted one clock late (one idle clock after the stop bit ends).
module cov_P22_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        s_axis_tvalid
);

  localparam logic [15:0] PS     = 16'd1;
  localparam logic [4:0]  PERIOD = 5'd7;
  localparam logic [1:0]  GAP    = 2'd1;

  reg [7:0] shift;
  reg       active;
  reg       done;
  reg       ok;
  reg [4:0] cyc;
  reg       first_ok;
  reg [1:0] idle_cnt;
  reg       second;

  always @(posedge clk) begin
    if (rst) begin
      shift    <= 8'h00;
      active   <= 1'b0;
      done     <= 1'b0;
      ok       <= 1'b0;
      cyc      <= 5'd0;
      first_ok <= 1'b0;
      idle_cnt <= 2'd0;
      second   <= 1'b0;
    end else begin
      done <= 1'b0;
      if (prescale_reg == 19'd0) begin
        cyc <= 5'd0;
      end else if (cyc != 5'd31) begin
        cyc <= cyc + 5'd1;
      end
      if (done && ok && shift == 8'h96 && prescale == PS) begin
        first_ok <= 1'b1;
        idle_cnt <= 2'd0;
      end
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
        active   <= (prescale == PS);
        shift    <= 8'h00;
        ok       <= 1'b1;
        second   <= first_ok && (idle_cnt == GAP);
        first_ok <= 1'b0;
        idle_cnt <= 2'd0;
      end else begin
        if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && first_ok && idle_cnt != 2'd3) begin
          idle_cnt <= idle_cnt + 2'd1;
        end
        if (active && prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
          shift <= {txd, shift[7:1]};
          if (cyc != PERIOD) begin
            ok <= 1'b0;
          end
          if (bit_cnt == 4'd1) begin
            done   <= 1'b1;
            active <= 1'b0;
          end
        end
      end
      if (prescale != PS) begin
        active   <= 1'b0;
        first_ok <= 1'b0;
        second   <= 1'b0;
      end
    end
  end

  P22_twin_tx_b2b_one_clock_late: cover property (@(posedge clk) disable iff (rst)
    done && ok && second && shift == 8'h69 && txd && bit_cnt == 4'd0 &&
    prescale == 16'd1);

endmodule

bind uart_tx cov_P22_twin u_cov_P22_twin (.*);
